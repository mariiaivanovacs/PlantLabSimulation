"""Decision-making logic"""

from .rules import evaluate_rules

class Planner:
    """Agent planner for decision-making"""
    
    def __init__(self):
        self.history = []
    
    def plan(self, state, environment):
        """Generate action plan based on current state"""
        actions = []
        
        # Use rule-based system
        actions = evaluate_rules(state, environment)
        
        self.history.append({
            'state': state,
            'actions': actions
        })
        
        return actions
    
    def get_history(self):
        """Get planning history"""
        return self.history

