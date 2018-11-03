import hlt
from hlt import constants, Game
from hlt.positionals import Position, Direction
from hlt.game_map import GameMap, Player, MapCell
from hlt.entity import Ship
from modes import Modes
import logging
import random


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
        self.PROD_STOP_TURN = 220
        self.game_mode = Modes.NORMAL

    def state(self, ship):
        return self.ship_states[ship.id]

    def closest_dropoff(self, ship):
        min_dist = 9000
        closest_base = None
        for base in self.bases:
            if self.game_map.calculate_distance(ship.position, base.position) < min_dist:
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
        turns_to_recall = self.farthest_ship_distance() + len(self.ships)* 0.3
        turns_left = constants.MAX_TURNS - self.game.turn_number
        if turns_left < turns_to_recall:
            for ship in self.ships:
                self.game_mode = Modes.ENDGAME
                self.ship_states[ship.id].destination = self.closest_dropoff(ship)

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
        self.command_queue = []
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
        self.ship_states[ship.id].destination = random.choice(self.top_clusters).position

    def unstuck(self, ship: Ship):
        pass

    def leave_dropoff(self, ship):
        """
        Command a ship to leave a dropoff only moving to a safe cell
        """
        possible_dests = ship.position.get_surrounding_cardinals()
        random.shuffle(possible_dests)
        move = self.move_safe(ship, possible_dests)
        self.command(ship.move(move))

    def dropoff_surrounded(self, dropoff: Position):
        if self.game_map[dropoff].is_occupied:
            adjacent_cells = dropoff.get_surrounding_cardinals()
            adj_cells_occupied = [
                self.game_map[cell].is_occupied for cell in adjacent_cells
            ]
            if adj_cells_occupied.count(True) == 4:
                return True
        return False

    def richest_clusters(self, top_n: int = 5):
        """returns a list of top clusters"""
        spread_clusters = {}
        for x in range(self.game_map.width):
            if x == 1 or (x-1)%3 == 0:
                for y in range(self.game_map.height):
                    if y == 1 or (y-1)%3 == 0:
                        cell = self.game_map[Position(x,y)]
                        spread_clusters[Position(x,y)] = Cluster(self.game_map, cell)

        sorted_cells = sorted(spread_clusters.values(), reverse=True)
        sorted_cells = sorted_cells[:top_n]
        logging.info(sorted_cells)
        
        self.top_clusters = sorted_cells

    def _reset_current_moves(self):
        [ship.reset_moves() for ship in self.ship_states.values()]

    def command(self, command):
        self.command_queue.append(command)

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

    def navigate_max_halite(self, ship):
        destination = self.ship_states[ship.id].destination
        possible_moves = self.game_map.get_unsafe_moves(ship.position, destination)
        possible_positions = [ship.position.directional_offset(move) for move in possible_moves]
        halite_locations = {position: self.game_map[position].halite_amount
                            for position in possible_positions}
        halite_locations[ship.position] = self.game_map[ship.position].halite_amount * 1.8
        new_positions = sorted(halite_locations, key=halite_locations.get, reverse=True)
        
        move = self.move_safe(ship, new_positions)
        # prevent from moving back on to dropoff
        move = self.avoid_dropoffs(ship, move)
        self.command(ship.move(move))
        

    def avoid_dropoffs(self, ship, move):
        move_cell = self.game_map[ship.position.directional_offset(move)]
        if move_cell.has_structure:
            move_cell.ship = None
            new_move = self.avoid(move)
            return new_move
        return move

    def move_safe(self, ship, positions):
        """ 
        Chooses first safe cell in directions list to navigat into
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
        positions = [ship.position.directional_offset(direction) for direction in directions]
        for i, cell in enumerate(positions):
            if not self.game_map[cell].is_occupied:
                self.game_map[cell].mark_unsafe(ship)
                return directions[i]
        return Direction.Still   

    def report_game_state(self):
        logging.info(f"Game State: {self.game_mode}")


    def adjacent_dest(self, ship):
        dest = self.ship_states[ship.id].destination
        dest_cards = dest.get_surrounding_cardinals()
        return ship.position in dest_cards

    def stay_still(self, ship: Ship):
        self.command(ship.stay_still())

    def navigate_bline(self, ship):
        destination = self.ship_states[ship.id].destination
        move = self.game_map.naive_navigate(ship, destination)
        self.command(ship.move(move))

    def deposit_complete(self, ship):
        return (self.going_home(ship)) and (ship.halite_amount == 0)

    def dest_halite(self, ship):
        return self.game_map[self.ship_states[ship.id].destination].halite_amount

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
            self.command(ship.move(moves[0]))
        else:
            logging.info(f"ship at dropoff {ship.position == destination}, ")


class Cluster:
    def __init__(self, game_map: GameMap, center_cell: MapCell):
        self.game_map = game_map
        self.cluster_center = center_cell
        self.cluster = [center_cell]
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
        return (sum([cell.halite_amount for cell in self.cluster]))

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
        self.preferred_move = None #not currently implemented

    def reset_moves(self):
        self.current_move = None

    def __repr__(self):
        return f"ShipState(mode: {self.mode}, prev_move:{self.prev_move}"
