#!/usr/bin/env python3
# Python 3.6
import hlt
from hlt import constants
from hlt.positionals import Direction, Position
from hlt.game_map import GameMap
import random
import logging
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

game.ready("Snowcola V4")

# Now that your bot is initialized, save a message to yourself in the log file with some important information.
#   Here, you log here your id, which you can always fetch from the game object by using my_id.
logging.info("Successfully created bot! My Player ID is {}.".format(
    game.my_id))
""" <<<Game Loop>>> """
ship_states = {}
MAX_HALITE = constants.MAX_HALITE
endstage = constants.MAX_TURNS - 10
shipyard_cards = game.me.shipyard.position.get_surrounding_cardinals()
logging.info(shipyard_cards)
while True:
    logging.warn(f"states: {ship_states}")
    game.update_frame()
    me = game.me
    game_map = game.game_map
    logging.info(game_map)
    # calculate how many turns it will take the farthest ship to deposit its
    # halite if it starts now
    turns_left = constants.MAX_TURNS - game.turn_number
    ships = me.get_ships()
    if ships:
        furthest_ship_turns = game_map.turns_to_farthest_ship(
            ships, me.shipyard.position)

    confirmed_moves = []

    command_queue = []

    for ship in me.get_ships():
        if ship.id not in ship_states.keys():
            ship_states[ship.id] = 'harvest'

        if ship.halite_amount > MAX_HALITE * 0.9:
            ship_states[ship.id] = 'dump'

        if turns_left <= furthest_ship_turns:
            ship_states[ship.id] = 'endgame'

        if ship_states[ship.id] == 'endgame':
            #logging.warn("ENDGAME")
            #move = game_map.naive_navigate(ship, me.shipyard.position)
            #command_queue.append(ship.move(move))

            if ship.position in shipyard_cards:
                game_map[me.shipyard.position].ship = None

            #move = game_map.naive_navigate(ship, Position(0,0))
            #command_queue.append(ship.move(move))

        elif ship_states[ship.id] == 'harvest':
            logging.info(f"Ship: {ship.id} Harvesting")
            if game_map[ship.position].halite_amount < MAX_HALITE * 0.10:

                logging.info(f"""{ship.id} moving, not enough halite HAL: 
                {game_map[ship.position].halite_amount}""")

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
                else:
                    logging.info(f"{ship.id} stopping to avoid collision")
                    best_direction = Direction.Still
                    confirmed_moves.append(ship.position)
                    command_queue.append(ship.stay_still())

            else:
                logging.info(f"{ship.id} stopping to collect halite")
                command_queue.append(ship.stay_still())

        elif ship_states[ship.id] == 'dump':
            logging.info(f"{ship.id} going to unload")
            if ship.halite_amount > 0:
                move = game_map.naive_navigate(ship, me.shipyard.position)
                command_queue.append(ship.move(move))

            else:
                ship_states[ship.id] = 'harvest'
                move = game_map.naive_navigate(ship, Position(0, 0))
                command_queue.append(ship.move(move))

    # If the game is in the first 200 turns and you have enough halite, spawn a ship.
    # Don't spawn a ship if you currently have a ship at port, though - the ships will collide.
    if game.turn_number <= 220 and me.halite_amount >= constants.SHIP_COST and not game_map[me.
                                                                                            shipyard].is_occupied:
        command_queue.append(me.shipyard.spawn())

    # Send your moves back to the game environment, ending this turn.
    game.end_turn(command_queue)
