import os
import sys
import re

def find_executable(cmd): # looks for location of a command in the PATH
    for path in os.environ.get("PATH", "").split(":"):
        exe_path = os.path.join(path, cmd) # combines path and command
        if os.access(exe_path, os.X_OK): #checks if the file is executable
            return exe_path
    return None

def execute_command(command):
    command = command.strip()
    if not command:
        return  

    match = re.search(r'>(\s*\S+)', command) # Redirect output to a file if >
    output_file = match.group(1).strip() if match else None
    command = command.split(">")[0].strip() if match else command

    match = re.search(r'<(\s*\S+)', command) # Redirect input to a file if <
    input_file = match.group(1).strip() if match else None
    command = command.split("<")[0].strip() if match else command

    background = bool(re.search(r'\s&$', command)) # command ends with '&' it'll run in the background
    command = command.rstrip("&").strip()

    args = re.findall(r'[^"\s]\S*|".+?"', command) # Split command into arguments (ignoring quotes)
    args = [arg.strip('"') for arg in args]

    if "|" in command: # Check if command is a pipeline
        commands = [cmd.strip() for cmd in command.split("|")] # Split command into multiple commands
        num_pipes = len(commands) - 1
        pipes = [os.pipe() for _ in range(num_pipes)] #create pair of file descriptors (input,output)
        pids = []

        for i, cmd in enumerate(commands): # Execute each command in the pipeline
            cmd_args = re.findall(r'[^"\s]\S*|".+?"', cmd) 
            cmd_args = [arg.strip('"') for arg in cmd_args] # Split command into arguments
            pid = os.fork() # create child process for each command to run concurrently
            if pid == 0:
                if i > 0: # not first command in the pipeline
                    os.dup2(pipes[i - 1][0], sys.stdin.fileno()) # read end of previous pipe
                if i < num_pipes: # not last command in the pipeline
                    os.dup2(pipes[i][1], sys.stdout.fileno()) # send output to next command
                for read_fd, write_fd in pipes: # Close all pipes
                    os.close(read_fd)
                    os.close(write_fd)
                exec_path = find_executable(cmd_args[0]) if '/' not in cmd_args[0] else cmd_args[0] # Check if command is in PATH
                if not exec_path: 
                    print(f"{cmd_args[0]}: command not found", file=sys.stderr)
                    sys.exit(127)
                try: # Execute command
                    os.execve(exec_path, cmd_args, os.environ)
                except OSError as e: # Error if command fails
                    print(f"{cmd_args[0]}: {os.strerror(e.errno)}", file=sys.stderr)
                    sys.exit(e.errno)
            else:
                pids.append(pid) # Add child process ID to list

        for read_fd, write_fd in pipes: # Close all pipes
            os.close(read_fd)
            os.close(write_fd)
        for pid in pids:
            os.waitpid(pid, 0) # Wait for all child processes to finish
        return

    if args[0] == "exit": 
        sys.exit(0)

    if args[0] == "cd": 
        try: # Change directory
            target_dir = args[1] if len(args) > 1 else os.environ.get("HOME", "/")
            os.chdir(target_dir)
        except IndexError: # Change to home directory if no arguments
            os.chdir(os.environ.get("HOME", "/"))
        except FileNotFoundError: # Error if directory doesn't exist
            print(f"cd: no such file or directory: {target_dir}", file=sys.stderr)
        return

    original_stdin = os.dup(0) # Save original stdin and stdout
    original_stdout = os.dup(1)

    pid = os.fork() # child process executes command with redirection
    if pid == 0:
        try:
            if input_file: 
                fd = os.open(input_file, os.O_RDONLY)
                os.dup2(fd, 0) # to read from the file 
                os.close(fd)
            if output_file:
                fd = os.open(output_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
                os.dup2(fd, 1) # write into the file
                os.close(fd)
            exec_path = args[0] if os.path.isfile(args[0]) and os.access(args[0], os.X_OK) else find_executable(args[0]) #Checks if it's a valid file
            if not exec_path:
                print(f"{args[0]}: command not found", file=sys.stderr)
                sys.exit(127)
            os.execve(exec_path, args, os.environ)
        except OSError as e:
            print(f"{args[0]}: {os.strerror(e.errno)}", file=sys.stderr)
            sys.exit(e.errno)
    else:
        if background:
            print(f"[{pid}] running in background") # Print background process ID
        else:
            os.waitpid(pid, 0) # Wait for child process to finish

        os.dup2(original_stdin, 0)
        os.dup2(original_stdout, 1)
        os.close(original_stdin)
        os.close(original_stdout)

def main(): # Continuously asks for user input and executes commands
    while True:
        try:
            PS1 = os.environ.get("PS1", "$ ")
            command = input(PS1).strip()
            if command:
                execute_command(command)
        except EOFError:
            print()
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()