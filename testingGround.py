class ShipState:
    def __init__(self, mode, prev_move=None):
        self.mode = mode
        self.prev_move = prev_move
    
    def __repr__(self):
        return f"ShipState(mode: {self.mode}, prev_move:{self.prev_move}"