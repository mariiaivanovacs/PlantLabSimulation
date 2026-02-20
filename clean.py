import os

# Set the directory you want to work on
folder_path = "."  # current folder, change if needed

# Loop through all items in the folder
for filename in os.listdir(folder_path):
    file_path = os.path.join(folder_path, filename)
    
    # Only process files, skip folders
    if os.path.isfile(file_path):
        # Ask the user if they want to delete the file
        choice = input(f"Do you want to delete '{filename}'? (y/n): ").strip().lower()
        if choice == 'y':
            try:
                os.remove(file_path)
                print(f"Deleted '{filename}'")
            except Exception as e:
                print(f"Failed to delete '{filename}': {e}")
        else:
            print(f"Skipped '{filename}'")