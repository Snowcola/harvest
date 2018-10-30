#!/usr/bin/env python3
# Python 3.6
import hlt
from hlt import constants
from hlt.positionals import Direction, Position
from hlt.game_map import GameMap, Player, MapCell
from hlt.entity import Entity, Ship
import random
import logging
from modes import Modes


class Navigation:
    def __init__(self, gameMap: GameMap, player: Player):
        self.game_map = gameMap
        self.player = player
        self.ships = player.get_ships()
        self.bases = [player.shipyard] + player.get_dropoffs()
        logging.info(f"ships :{player.get_dropoffs()+[self.player.shipyard]}")

    def farthest_ship_distance(self) -> int:
        bases = self.bases
        ships = self.ships
        if ships and bases:
            max_distances = []
            for base in bases:
                distances = [
                    self.game_map.calculate_distance(ship.position,
                                                     base.position)
                    for ship in ships
                ]
                max_distance = max(distances)
                max_distances.append(max_distance)

            return max(max_distances)
        else:
            return 0

    def start_positions(self):
        staring_positions = self.player.shipyard.position.get_surrounding_cardinals()
        return staring_positions

    def can_afford_move(self, ship: Ship):
        location_halite = self.game_map[ship.position].halite_amount
        move_cost = location_halite * 0.1
        return ship.halite_amount >= move_cost

    def low_hal_location(self, ship):
        return self.game_map[ship.position].halite_amount < constants.MAX_HALITE * 0.1

    def should_move(self, ship: Ship):
        return self.can_afford_move(ship) and self.low_hal_location(ship)


    def update(self, game_map: GameMap, player: Player):
        self.game_map = game_map
        self.player = player

    def select_move_hueristic(self, ship: Ship):
        surrounding_positions = ship.position.get_surrounding_cardinals()
        current_position = ship.position
        halite_locations = {(position):self.game_map[position].halite_amount for position in surrounding_positions}
        halite_locations[current_position] = self.game_map[current_position].halite_amount * 1.8
        new_position = max(halite_locations, key=halite_locations.get)
        return new_position #
        
        # check surrounding locations
        # for each location chech halite ammount

    def select_move_richness(self, ship: Ship):
        pass

    def cluster_map(self, top_n: int = 10):
        """returns a list of top clusters"""
        all_halite = {cell.position:Cluster(self.game_map, cell).halite_amount for cell in self.game_map}
        sorted_cells = sorted(all_halite, key=all_halite.get, reverse=True)
        sorted_cells = sorted_cells[:top_n]
        top_clusters = [Cluster(self.game_map, self.game_map[cell]) for cell in sorted_cells]

        return top_clusters


class Cluster:
    def __init__(self, game_map: GameMap, center_cell: MapCell):
        self.game_map = game_map
        self.cluster_center = center_cell
        self.cluster = [center_cell]
        for x in range(-1,2):
            for y in range(-1,2):
                try:
                    cell = self.game_map[self.cluster_center.position.directional_offset((x,y))]
                    self.cluster.append(cell)                 
                except Exception:
                    logging.warn(f"can't find cell at {(x,y)}")
        

    @property
    def halite_amount(self):
        """
        :return: total halite amount in 9 cell cluster
        """
        return (sum([cell.halite_amount for cell in self.cluster]))

    def __repr__(self):
        return f"Cluster {self.cluster_center}, halite: {self.halite_amount}"


class ShipState:
    def __init__(self, mode, prev_move=None):
        self.mode = mode
        self.prev_move = prev_move
        self.current_move = None

    def reset_moves(self):
        self.current_move = None
    
    def __repr__(self):
        return f"ShipState(mode: {self.mode}, prev_move:{self.prev_move}"

## RANDOMIZE NAVIGATION DIRECTION

""" <<<Game Begin>>> """

# This game object contains the initial game state.
game = hlt.Game()
# At this point "game" variable is populated with initial map data.
# This is a good place to do computationally expensive start-up pre-processing.
# As soon as you call "ready" function below, the 2 second per turn timer will start.
directions = [
    Direction.North, Direction.South, Direction.East, Direction.West,
    Direction.Still
]

MAX_HALITE = constants.MAX_HALITE
MAX_TURNS = constants.MAX_TURNS
game.ready("Snowcola_v4")

# Now that your bot is initialized, save a message to yourself in the log file with some important information.
#   Here, you log here your id, which you can always fetch from the game object by using my_id.
logging.info("Successfully created bot! My Player ID is {}.".format(
    game.my_id))
""" <<<Game Loop>>> """

ship_states = {}
endstage = constants.MAX_TURNS - 10
shipyard_cards = game.me.shipyard.position.get_surrounding_cardinals()
logging.info(directions[:4])

nav = Navigation(game.game_map, game.me)
logging.info(f"Cluster Map {nav.cluster_map()}")
while True:

    game.update_frame()
    me = game.me
    game_map = game.game_map
    nav.update(game_map, me)

    confirmed_moves = []
    command_queue = []

    # reset current moves in ship state
    [shipstate.reset_moves() for shipstate in ship_states.values()]
    
    turns_to_recall = nav.farthest_ship_distance()+len(ship_states)*0.5

    for ship in me.get_ships():
        cur_loc_halite = game_map[ship.position].halite_amount


        if ship.id not in ship_states.keys():
            ship_states[ship.id] = ShipState(Modes.collecting)

        prev_move = ship_states[ship.id].prev_move

        if MAX_TURNS - game.turn_number <= turns_to_recall:
            if ship.position in shipyard_cards:
                move = game_map.naive_navigate(ship, me.shipyard.position)
                command_queue.append(ship.move(move))
                game_map[me.shipyard.position].ship = None
            else:
                move = game_map.naive_navigate(ship, random.choice(shipyard_cards))
                command_queue.append(ship.move(move))

        elif ship_states[ship.id].mode == Modes.collecting:
            if ship.halite_amount > MAX_HALITE * 0.95:
                ship_states[ship.id].mode = Modes.depositing


            if nav.should_move(ship):
                destination = nav.select_move_hueristic(ship)

                if destination not in confirmed_moves:
                    if prev_move is not Direction.Still:
                        confirmed_moves.append(destination)
                        move = game_map.naive_navigate(ship, destination)
                        command_queue.append(ship.move(move))
                        ship_states[ship.id].prev_move = move
                    else: 
                        dest = ship.position.directional_offset(random.choice(directions))
                        move = game_map.naive_navigate(ship, dest)
                        ship_states[ship.id].prev_move = move
                        command_queue.append(ship.move(move))
                else:
                    best_direction = Direction.Still
                    confirmed_moves.append(ship.position)
                    command_queue.append(ship.stay_still())

            else:
                command_queue.append(ship.stay_still())

        elif ship_states[ship.id].mode == Modes.depositing:
            if ship.halite_amount > 0:
                move = game_map.naive_navigate(ship, me.shipyard.position)
                command_queue.append(ship.move(move))

            else:
                ship_states[ship.id].mode = Modes.collecting
                move = game_map.naive_navigate(ship, Position(0, 0))
                command_queue.append(ship.move(move))

    # If the game is in the first 200 turns and you have enough halite, spawn a ship.
    # Don't spawn a ship if you currently have a ship at port, though - the ships will collide.
    if game.turn_number <= 220 and me.halite_amount >= constants.SHIP_COST and not game_map[me.
                                                                                            shipyard].is_occupied:
        command_queue.append(me.shipyard.spawn())

    # Send your moves back to the game environment, ending this turn.
    game.end_turn(command_queue)
