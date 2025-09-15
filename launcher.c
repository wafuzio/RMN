#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <libgen.h>

int main(int argc, char *argv[]) {
    // Get the path to this executable
    char *exec_path = realpath(argv[0], NULL);
    if (!exec_path) {
        fprintf(stderr, "Failed to get executable path\n");
        return 1;
    }
    
    // Navigate up from .../Kroger TOA Scraper.app/Contents/MacOS/launcher
    // to get to the project directory
    char *app_bundle_dir = dirname(dirname(dirname(exec_path)));
    char *project_dir = dirname(app_bundle_dir);
    
    // Change to project directory
    if (chdir(project_dir) != 0) {
        fprintf(stderr, "Failed to change to project directory: %s\n", project_dir);
        free(exec_path);
        return 1;
    }
    
    // Build the command to execute
    char command[1024];
    snprintf(command, sizeof(command), 
        "python3 -c \""
        "import sys; "
        "sys.path.insert(0, '%s'); "
        "import keyword_input; "
        "import tkinter as tk; "
        "root = tk.Tk(); "
        "app = keyword_input.KeywordInputApp(root); "
        "root.mainloop()"
        "\"", project_dir);
    
    free(exec_path);
    
    // Execute the Python command
    return system(command);
}
