#!/usr/bin/env python3
# Python 3.6
import hlt
from hlt import constants
from hlt.positionals import Direction, Position
from hlt.game_map import GameMap, Player
from hlt.entity import Entity

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


class ShipState:
    def __init__(self, mode, prev_move=None):
        self.mode = {}
        self.prev_move = {}
    
    def __repr__()


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

game.ready("Snowcola")

# Now that your bot is initialized, save a message to yourself in the log file with some important information.
#   Here, you log here your id, which you can always fetch from the game object by using my_id.
logging.info("Successfully created bot! My Player ID is {}.".format(
    game.my_id))
""" <<<Game Loop>>> """

ship_states = {}
endstage = constants.MAX_TURNS - 10
shipyard_cards = game.me.shipyard.position.get_surrounding_cardinals()
logging.info(shipyard_cards)

while True:

    game.update_frame()

    confirmed_moves = []

    me = game.me
    game_map = game.game_map

    command_queue = []

    nav = Navigation(game_map, me)
    logging.info(ship_states)
    logging.info(f"Turns {nav.farthest_ship_distance()}")

    for ship in me.get_ships():
        if ship.id not in ship_states.keys():
            ship_states[ship.id] = ShipState(Modes.collecting)

        if game.turn_number > endstage:
            move = game_map.naive_navigate(ship, me.shipyard.position)
            command_queue.append(ship.move(move))

            if ship.position in shipyard_cards:
                game_map[me.shipyard.position].ship = None

        elif ship_states[ship.id].mode == Modes.collecting:
            if ship.halite_amount > constants.MAX_HALITE * 0.9:
                ship_states.mode[ship.id] = Modes.depositing

            if game_map[ship.
                        position].halite_amount < constants.MAX_HALITE * 0.10:
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
                    confirmed_moves.append(destination)
                    move = game_map.naive_navigate(ship, destination)
                    command_queue.append(ship.move(move))
                    ship_states[ship.id].prev_move = move
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
