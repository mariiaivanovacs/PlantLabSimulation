"""CLI entry point (optional)"""

import sys
from cli.commands import run_simulation, list_plants

def main():
    """Main CLI entry point"""
    if len(sys.argv) < 2:
        print("Plant Simulator CLI")
        print("\nUsage:")
        print("  python main.py list                    - List available plants")
        print("  python main.py run [plant] [days]      - Run simulation")
        print("\nExamples:")
        print("  python main.py list")
        print("  python main.py run tomato 30")
        return
    
    command = sys.argv[1]
    
    if command == 'list':
        list_plants()
    elif command == 'run':
        plant = sys.argv[2] if len(sys.argv) > 2 else 'tomato'
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        run_simulation(plant, days)
    else:
        print(f"Unknown command: {command}")

if __name__ == '__main__':
    main()

