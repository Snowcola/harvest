import hlt
from hlt import constants, Game
from hlt.positionals import Position, Direction
from hlt.game_map import GameMap, Player, MapCell
from hlt.entity import Ship
from modes import Modes
import logging
import random
import math

CLUSTER_TOBASE = 3
BASE_POXIMITY_MULTIPLIER = 5
STAY_STILL_WEIGHT = 1.8
PROD_STOP_TURN = 220


class Navigation:
    def __init__(self, game: Game):
        self.game = game
        self.game_map = game.game_map
        self.player = game.me
        self.ships = game.me.get_ships()
        self.bases = [game.me.shipyard] + game.me.get_dropoffs()
        self.ship_states = {}  # {ship.id: ShipState()}
        self.top_clusters = None
        self.command_queue = []
        self.PROD_STOP_TURN = PROD_STOP_TURN
        self.game_mode = Modes.NORMAL
        self.commands = {}  #{ship.id: (move)}
        self.commands_queue = {}  # {ship.id: command}
        self.total_halite = 0
        self.inital_halite = 0
        self.used_positions = []

    def state(self, ship):
        return self.ship_states[ship.id]

    def mark_enemy_adjacent_unsafe(self):
        for bot in self.game:
            if bot.id is not self.player.id:
                for ship in bot.get_ships():
                    north = ship.position.directional_offset(Direction.North)
                    east = ship.position.directional_offset(Direction.East)
                    south = ship.position.directional_offset(Direction.South)
                    west = ship.position.directional_offset(Direction.West)
                    for cell in [north, east, south, west]:
                        self.game_map[cell].mark_unsafe(ship)

    def closest_dropoff(self, ship):
        min_dist = 9000
        closest_base = None
        for base in self.bases:
            if self.game_map.calculate_distance(ship.position,
                                                base.position) < min_dist:
                closest_base = base
        return closest_base.position

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

    def check_endgame(self):
        turns_to_recall = self.farthest_ship_distance() + len(self.ships) * 0.3
        turns_left = constants.MAX_TURNS - self.game.turn_number
        if turns_left < turns_to_recall:
            for ship in self.ships:
                self.game_mode = Modes.ENDGAME
                self.ship_states[ship.id].destination = self.closest_dropoff(
                    ship)

    def _initialize_ship_states(self):
        """initialize all newly created ships with a default ship state"""
        for ship in self.ships:
            if ship.id not in self.ship_states:
                state = ShipState(Modes.COLLECTING)
                self.ship_states[ship.id] = state

    def start_positions(self):
        staring_positions = self.player.shipyard.position.get_surrounding_cardinals(
        )
        return staring_positions

    def avoid(self, destination):
        if destination is Direction.North or destination is Direction.South:
            return self.safe_direction([Direction.East, Direction.West])
        elif destination is Direction.West or destination is Direction.East:
            return self.safe_direction([Direction.North, Direction.South])
        else:
            return Direction.Still

    def can_afford_move(self, ship: Ship):
        location_halite = self.game_map[ship.position].halite_amount
        move_cost = location_halite * 0.1
        return ship.halite_amount >= move_cost

    def low_hal_location(self, ship: Ship):
        return self.game_map[ship.
                             position].halite_amount < constants.MAX_HALITE * 0.1
        # TODO: MAKE THIS BASED ON A USER DEFINED PARAM

    def should_move(self, ship: Ship):
        return self.can_afford_move(ship) and self.low_hal_location(ship)

    def update(self, game: hlt.Game):
        """update all game data and reset turn specific info"""
        self.game_map = game.game_map
        self.player = game.me
        self.ships = game.me.get_ships()
        self.calc_total_halite()
        self.command_queue = []
        self.commands = {}
        self.commands_queue = {}
        self._initialize_ship_states()
        self._reset_current_moves()
        self.richest_clusters()
        self.check_endgame()

    def select_move_hueristic(self, ship: Ship, destination: Position = None):
        surrounding_positions = ship.position.get_surrounding_cardinals()
        if destination:
            # should trigger recalc of map here is this evals to none
            direction_of_cluster = self.game_map._get_target_direction(
                ship.position, destination)
            best_positions = [
                ship.position.directional_offset(direction)
                for direction in direction_of_cluster if direction is not None
            ]
            if best_positions is not None:
                surrounding_positions = best_positions
        current_position = ship.position
        halite_locations = {(position): self.game_map[position].halite_amount
                            for position in surrounding_positions}
        halite_locations[current_position] = self.game_map[
            current_position].halite_amount * 1.8
        new_position = max(halite_locations, key=halite_locations.get)
        return new_position  #

    def select_rich_destination(self, ship: Ship):
        # get closest cluster to ship
        closest_cluster = None
        distance_to_cluster = self.game_map.width
        for cluster in self.top_clusters:
            distance = self.game_map.calculate_distance(
                ship.position, cluster.position)
            if distance < distance_to_cluster:
                distance_to_cluster = distance
                closest_cluster = cluster
        #self.ship_states[ship.id].destination = closest_cluster.rich_position
        self.ship_states[ship.id].destination = random.choice(
            self.top_clusters).position

    def unstuck(self, ship: Ship):
        pass

    def leave_dropoff(self, ship):
        """
        Command a ship to leave a dropoff only moving to a safe cell
        """
        possible_dests = ship.position.get_surrounding_cardinals()
        random.shuffle(possible_dests)
        self.ship_states[ship.id].preferred_move = possible_dests[0]
        move = self.move_safe(ship, possible_dests)
        self.command(ship, ship.move(move), move=move)

    def dropoff_surrounded(self, dropoff: Position):
        if self.game_map[dropoff].is_occupied:
            adjacent_cells = dropoff.get_surrounding_cardinals()
            adj_cells_occupied = [
                self.game_map[cell].is_occupied for cell in adjacent_cells
            ]
            if adj_cells_occupied.count(True) == 4:
                return True
        return False

    def calc_straight_distance(self, source: Position, dest: Position):
        source = self.game_map.normalize(source)
        dest = self.game_map.normalize(dest)
        direction_vector = abs(source - dest)
        shortest_x = min(direction_vector.x,
                         self.game_map.width - direction_vector.x)
        shortest_y = min(direction_vector.y,
                         self.game_map.height - direction_vector.y)
        return math.sqrt(shortest_x**2 + shortest_y**2)

    def calc_total_halite(self):
        total_halite = 0
        for cell in self.game_map:
            total_halite += cell.halite_amount
        self.total_halite = total_halite
        if self.inital_halite == 0:
            self.inital_halite = total_halite

    def richest_clusters(self, top_n: int = 5):
        """returns a list of top clusters"""
        spread_clusters = {}
        for x in range(self.game_map.width):
            if x == 1 or (x - 1) % 3 == 0:
                for y in range(self.game_map.height):
                    if y == 1 or (y - 1) % 3 == 0:
                        cell = self.game_map[Position(x, y)]
                        spread_clusters[Position(x, y)] = Cluster(
                            self.game_map, cell)

        for position, cluster in spread_clusters.items():
            distance = self.calc_straight_distance(
                position, self.player.shipyard.position)
            if distance < self.game_map.width / CLUSTER_TOBASE:
                cluster.halite_multiplier = BASE_POXIMITY_MULTIPLIER

        sorted_cells = sorted(spread_clusters.values(), reverse=True)
        sorted_cells = sorted_cells[:top_n]

        self.top_clusters = sorted_cells

    def _reset_current_moves(self):
        [ship.reset_moves() for ship in self.ship_states.values()]

    def command(self, ship, command, move=None):
        self.commands[ship.id] = move
        self.commands_queue[ship.id] = command
        self.command_queue.append(command)
        if move:
            self.used_positions.append(ship.position + Position(*move))

    def can_produce(self):
        return (self.game.turn_number <= self.PROD_STOP_TURN
                and self.player.halite_amount >= constants.SHIP_COST
                and not self.game_map[self.player.shipyard].is_occupied)

    def go_home(self, ship) -> Position:
        """
        Set destination to closest dropoff point \n
        Changes mode to 'deositing'
        """
        self.ship_states[ship.id].destination = self.closest_dropoff(ship)
        self.ship_states[ship.id].mode = Modes.DEPOSITING

    def going_home(self, ship):
        base_poitions = [base.position for base in self.bases]
        return ship.position in base_poitions

    @property
    def halite_per_cell(self):
        return round(self.total_halite / self.game_map.width**2)

    def navigate_max_halite(self, ship):
        # TODO: need to add logic to unmark spaces that we have left
        destination = self.ship_states[ship.id].destination
        possible_moves = self.game_map.get_unsafe_moves(
            ship.position, destination)
        possible_positions = [
            ship.position.directional_offset(move) for move in possible_moves
        ]
        halite_locations = {
            position: self.game_map[position].halite_amount
            for position in possible_positions
        }
        halite_locations[ship.position] = self.game_map[
            ship.position].halite_amount * STAY_STILL_WEIGHT
        new_positions = sorted(
            halite_locations, key=halite_locations.get, reverse=True)

        # add best move to preferred moves
        self.ship_states[ship.id].preferred_move = new_positions[0]

        move = self.move_safe(ship, new_positions)
        # prevent from moving back on to dropoff
        move = self.avoid_dropoffs(ship, move)
        self.command(ship, ship.move(move), move=move)

    def avoid_dropoffs(self, ship, move):
        move_cell = self.game_map[ship.position.directional_offset(move)]
        if move_cell.has_structure:
            move_cell.ship = None
            new_move = self.avoid(move)
            return new_move
        return move

    def mark_safe(self, position: Position):
        self.game_map[position].ship = None

    def move_safe(self, ship, positions):
        """ 
        Chooses first safe cell in directions list to navigate into
        """
        new_moves = []
        for position in positions:
            move = position - ship.position
            new_moves.append((move.x, move.y))

        for i, cell in enumerate(positions):
            if not self.game_map[cell].is_occupied:
                self.game_map[cell].mark_unsafe(ship)
                return new_moves[i]

        return Direction.Still

    def safe_direction(self, ship, directions):
        positions = [
            ship.position.directional_offset(direction)
            for direction in directions
        ]
        for i, cell in enumerate(positions):
            if not self.game_map[cell].is_occupied:
                self.game_map[cell].mark_unsafe(ship)
                return directions[i]
        return Direction.Still

    def report_game_state(self):
        logging.info(f"Game State: {self.game_mode}")
        logging.info(
            f"{round((1-self.total_halite/self.inital_halite)*100)}% of halite consumed {self.total_halite} remaining"
        )
        logging.info(f"{self.halite_per_cell} per cell")
        logging.info(f"{self.used_positions}")

    def adjacent_dest(self, ship):
        dest = self.ship_states[ship.id].destination
        dest_cards = dest.get_surrounding_cardinals()
        return ship.position in dest_cards

    def stay_still(self, ship: Ship):
        self.command(ship, ship.stay_still(), move=Direction.Still)

    def navigate_bline(self, ship):
        destination = self.ship_states[ship.id].destination
        unsafe_moves = self.game_map.get_unsafe_moves(ship.position,
                                                      destination)
        random.shuffle(unsafe_moves)
        if not unsafe_moves:
            self.ship_states[ship.id].preferred_move
        else:
            self.ship_states[
                ship.id].preferred_move = ship.position.directional_offset(
                    unsafe_moves[0])
        move = self.game_map.naive_navigate(ship, destination)
        self.command(ship, ship.move(move), move=move)

    def deposit_complete(self, ship):
        return (self.going_home(ship)) and (ship.halite_amount == 0)

    def dest_halite(self, ship):
        return self.game_map[self.ship_states[ship.id]
                             .destination].halite_amount

    def set_mode(self, ship, mode):
        self.ship_states[ship.id].mode = mode

    def on_dropoff(self, ship):
        base_positions = [base.position for base in self.bases]
        return ship.position in base_positions

    def kamikaze(self, ship):
        destination = self.ship_states[ship.id].destination
        moves = self.game_map.get_unsafe_moves(ship.position, destination)
        random.shuffle(moves)
        if moves:
            self.command(ship, ship.move(moves[0]), move=moves[0])
        else:
            logging.info(f"ship at dropoff {ship.position == destination}, ")

    def process_turn(self):
        swapped_ships = []
        for s_id, move in self.commands.items():
            logging.info
            if s_id and s_id >= 0 and s_id not in swapped_ships:
                ship = self.player.get_ship(s_id)
                ship_position = ship.position
                pref_dest = self.ship_states[s_id].preferred_move
                pref_move = pref_dest - ship_position

                # check if ship is stuck
                if move == Direction.Still and (
                        pref_move.x, pref_move.y) is not Direction.Still:
                    for other_ship in self.ships:
                        if other_ship.id is not s_id and other_ship.id not in swapped_ships and s_id not in swapped_ships and pref_dest == other_ship.position and self.ship_states[other_ship.
                                                                                                                                                                                    id].preferred_move == ship_position:
                            logging.warn(
                                f"ships: {s_id} and {other_ship.id} should swap"
                            )

                            swapped_ships.append(s_id)
                            swapped_ships.append(other_ship.id)
                            ship_move = other_ship.position - ship_position
                            other_ship_move = ship_position - other_ship.position

                            try:
                                self.commands_queue[s_id] = ship.move(
                                    (ship_move.x, ship_move.y))
                                self.commands_queue[
                                    other_ship.id] = other_ship.move(
                                        (other_ship_move.x, other_ship_move.y))
                            except IndexError:
                                logging.error(
                                    f"incorrect swap detected move {ship_move}  position {ship_position}"
                                )
                                logging.error(
                                    f"incorrect swap detected move {other_ship_move}  position {other_ship.position}"
                                )

        self.command_queue = self.commands_queue.values()


class Cluster:
    def __init__(self, game_map: GameMap, center_cell: MapCell):
        self.game_map = game_map
        self.cluster_center = center_cell
        self.cluster = [center_cell]
        self.halite_multiplier = 1
        for x in range(-1, 2):
            for y in range(-1, 2):
                try:
                    cell = self.game_map[
                        self.cluster_center.position.directional_offset((x,
                                                                         y))]
                    self.cluster.append(cell)
                except Exception:
                    logging.warn(f"can't find cell at {(x,y)}")

    @property
    def position(self):
        return self.cluster_center.position

    @property
    def rich_position(self):
        clusters = {
            cluster.position: cluster.halite_amount
            for cluster in self.cluster
        }
        high_val_pos = max(clusters, key=clusters.get)
        return high_val_pos

    @property
    def halite_amount(self):
        """
        :return: total halite amount in 9 cell cluster
        """
        return (sum([cell.halite_amount
                     for cell in self.cluster])) * self.halite_multiplier

    def __eq__(self, other):
        return self.halite_amount == other.halite_amount

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        return self.halite_amount > other.halite_amount

    def __ge__(self, other):
        return self.halite_amount >= other.halite_amount

    def __lt__(self, other):
        return self.halite_amount < other.halite_amount

    def __le__(self, other):
        return self.halite_amount <= other.halite_amount

    def __repr__(self):
        return f"Cluster {self.cluster_center}, halite: {self.halite_amount}"


class ShipState:
    def __init__(self, mode, destination=None, prev_move=None):
        self.mode = mode
        self.prev_move = prev_move
        self.current_move = None
        self.destination = destination
        self.preferred_move = None

    def reset_moves(self):
        self.current_move = None

    def __repr__(self):
        return f"ShipState(mode: {self.mode}, prev_move:{self.prev_move}"
