"""Turns decisions into simulation actions"""

from simulation.actions import apply_irrigation, apply_fertilizer, apply_light_control

class Executor:
    """Agent executor for applying actions"""
    
    def __init__(self):
        self.execution_log = []
    
    def execute(self, actions, environment):
        """Execute planned actions"""
        results = []
        
        for action in actions:
            action_type = action.get('type')
            
            if action_type == 'irrigate':
                environment = apply_irrigation(environment, action['amount'])
                results.append({'action': 'irrigate', 'status': 'success'})
            
            elif action_type == 'fertilize':
                environment = apply_fertilizer(environment, action['amount'])
                results.append({'action': 'fertilize', 'status': 'success'})
            
            elif action_type == 'light':
                environment = apply_light_control(environment, action['value'])
                results.append({'action': 'light', 'status': 'success'})
        
        self.execution_log.append(results)
        return environment, results
    
    def get_log(self):
        """Get execution log"""
        return self.execution_log

