import os
import sys
import shlex
#shell lexical analysis, parses strings like the syntax rules of a unix shell

def run_command(words):
    sys.stdout.flush() #anytext in internal output buffer is cleaned
    pid = os.fork()

    if pid == 0: #ensures child can run the process
        try:
            os.execvp(words[0], words)
        except OSError:
            print(f"shell: command not found: {words[0]}", file=sys.stderr)
            os._exit(127) #command not found
    else: #parent runs
        try:
#pauses parent(shell) until child terminates, and returns status code only
            _, status, _ = os.wait4(pid, 0)
        except KeyboardInterrupt:
            print()
            _, status, _ = os.wait4(pid, 0) 
#wait4 returns finished_pid, status_code, resource_usage
        if os.WIFEXITED(status): #checks whether child terminated normally 
            code = os.WEXITSTATUS(status) #extracts status code 8 bits
            if code != 0: #if errors pop up
                print(f"exit status {code}")
        elif os.WIFSIGNALED(status): #identifies if interrupts were made during running
            print(f"killed by signal {os.WTERMSIG(status)}")

def main():
    while True:
        try: #run code and watch out for errors
            line = input("shell> ")
        except EOFError:#ctrl D to close terminal
            print()
            break
        except KeyboardInterrupt: #ctrl C to start new line
            print()
            continue

        try:
            words = shlex.split(line)
        except ValueError: #no closing quotes
            print("shell: unmatched quote")
            continue
        if not words:
            continue
        if words[0] == "exit":
            break
        run_command(words)
        
if __name__=="__main__":
    main()