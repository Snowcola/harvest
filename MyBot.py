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

    def select_move_hueristic(self):

    def select_move_richness(self):

    def calc_cluster_values(game_map: GameMap) -> {"id": cluster_value: int}:

class Cluster:
    def __init__(self, game_map: GameMap, center_cell: MapCell):
        cluster_Center = center_cell
        cluster = [center_cell]
        for x in range(-1,2):
            for y in range(-1,2):
                cell = game_map[center_cell.position.directional_offset((x,y))]
                cluster.append(cell)
        self.cluster = cluster


class ShipState:
    def __init__(self, mode, prev_move=None):
        self.mode = mode
        self.prev_move = prev_move
    
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

while True:

    game.update_frame()
    me = game.me
    game_map = game.game_map
    nav.update(game_map, me)

    confirmed_moves = []
    command_queue = []

    
    turns_to_recall = nav.farthest_ship_distance()+len(ship_states)*0.5

    logging.info(f'ships {me.get_ships()}')

    for ship in me.get_ships():
        cur_loc_halite = game_map[ship.position].halite_amount


        if ship.id not in ship_states.keys():
            ship_states[ship.id] = ShipState(Modes.collecting)

        prev_move = ship_states[ship.id].prev_move

        if MAX_TURNS - game.turn_number <= turns_to_recall:
            move = game_map.naive_navigate(ship, me.shipyard.position)
            command_queue.append(ship.move(move))

            if ship.position in shipyard_cards:
                game_map[me.shipyard.position].ship = None

        elif ship_states[ship.id].mode == Modes.collecting:
            if ship.halite_amount > MAX_HALITE * 0.90:
                ship_states[ship.id].mode = Modes.depositing


            if nav.should_move(ship):
                halite_locations = {}
                cardinal_direction_map = {}
                for i, loc in enumerate(
                        ship.position.get_surrounding_cardinals() +
                    [ship.position]):
                    direction = directions[i]
                    if direction == Direction.Still:
                        halite = game_map[loc].halite_amount * 2
                    else:
                        halite = game_map[loc].halite_amount
                    halite_locations[direction] = halite
                    cardinal_direction_map[direction] = loc
                

                best_direction = max(
                    halite_locations, key=halite_locations.get)
                destination = cardinal_direction_map[best_direction]

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
