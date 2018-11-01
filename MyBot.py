#!/usr/bin/env python3
# Python 3.6
import hlt
from hlt import constants
from hlt.positionals import Direction
import logging
from modes import Modes
from navigation import Navigation

# This game object contains the initial game state.
game = hlt.Game()

# initialize constants
directions = [
    Direction.North, Direction.South, Direction.East, Direction.West,
    Direction.Still
]
MAX_HALITE = constants.MAX_HALITE
MAX_TURNS = constants.MAX_TURNS

# official game start
game.ready("Snowcola_v9")
# log bot id to log
logging.info("Successfully created bot! My Player ID is {}.".format(
    game.my_id))

# initialize map and starting cluster map
nav = Navigation(game)

#                 #
# Start Game Loop #
#                 #

while True:
    # get latest gamestate info from the halite engine
    game.update_frame()
    game_map = game.game_map
    me = game.me
    ships = me.get_ships()

    # update bot data
    nav.update(game)

    # set destinations

    # handout nav instructions

    if nav.can_produce():
        nav.command(me.shipyard.spawn())

    # Send your moves back to the game environment, ending this turn.
    game.end_turn(nav.command_queue)
