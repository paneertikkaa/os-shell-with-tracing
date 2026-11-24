import os
import sys
import shlex
import time
#shell lexical analysis, parses strings like the syntax rules of a unix shell

def parse_redirects(words):
    cmd = [] #actual command itself like ls/cat/etc
    infile = None #filename after < (slot 0, read kyb)
    outfile = None #filename after > or >> (slot 1, write to file)
    append = False #false when > (truncate) true when >> (append) 

    i = 0
    while i < len(words):
        w = words[i]
        if w in ("<", ">", ">>"):
            if i + 1 >= len(words) or words[i +1] in ("<", ">", ">>"):
                print(f"shell: syntax error: expected a filename after {w}")
                return None 
            target = words[i + 1]
            if w == "<":
                infile = target
            else: 
                outfile = target
                append = (w == ">>")
            i += 2
        else:
            cmd.append(w)
            i += 1
    if not cmd:
        print("shell: syntax error: missing command")
        return None
    return cmd, infile, outfile, append

def run_command(words, trace):
    sys.stdout.flush() #any text in internal output buffer is written out so child doesnt inherit
    start = time.monotonic() #stopwatch starts
    pid = os.fork()

    if pid == 0: #child runs the process
        try:
            if infile is not None:
                fd = os.open(infile, os.O_RDONLY)
                os.dup2(fd, 0)
                os.close(fd)
            if outfile is not None:
                flags = os.O_WRONLY | os.O_TRUNC
                flags |= os.O_APPEND if append else os.O_TRUNC
                fd = os.open(outfile, flag, 0o644)
                os.dup2(fd, 1)
                os.close(fd)
        except OSError as e:
            print(f"shell: {e.filename}: {e.strerror}", file=sys.stderr)
            os._exit(1)
        
        try:
            os.execvp(words[0], words)
        except FileNotFoundError:
            print(f"shell: command not found: {words[0]}", file=sys.stderr)
            os._exit(127)
        except PermissionError:
            print(f"shell: permission denied: {words[0]}", file=sys.stderr)
            os._exit(126)
        except OSError as e:
            print(f"shell: exec format error: {words[0]}: {e.strerror}", file=sys.stderr)
            os._exit(126)
    else: #parent runs
        try:
#pauses parent(shell) until child terminates, and returns status code and usage only
            _, status, usage = os.wait4(pid, 0)
        except KeyboardInterrupt:
            print()
            _, status, usage = os.wait4(pid, 0) 
        elapsed = time.monotonic() - start #stopwatch stopped
#wait4 returns finished_pid, status_code, resource_usage
        outcome = "unknown"
        if os.WIFEXITED(status): #checks whether child terminated normally 
            code = os.WEXITSTATUS(status) #extracts status code 8 bits
            outcome = f"exit {code}"
            if code != 0: #if errors pop up
                print(f"exit status {code}")
        elif os.WIFSIGNALED(status): #identifies if child was killed by signals
            outcome = f"signal {os.WTERMSIG(status)}"
            print(f"killed by signal {os.WTERMSIG(status)}")

        if trace:
            redir = ""
            if infile is not None:
                redir += f" in={infile}"
            if outfile is not None:
                redir += f"out={outfile}{' (append)' if append else ''}"
            print(
                f"trace: cmd={''.join(words)} pid={pid} "
                f"ppid={os.getpid()} outcome={outcome} time={elapsed:.3f}s " ##ppid is the shells id
                f"usage={usage.ru_utime + usage.ru_stime:.4f}s",
                file=sys.stderr,
            )

def main():
    trace = False #user needs to type trace on
    while True:
        try: #run code and watch out for errors
            line = input("shell> ")
        except EOFError:#ctrl D to close shell
            print()
            break
        except KeyboardInterrupt: #ctrl C to start new prompt
            print()
            continue

        try:
            words = shlex.split(line) #shlex recognizes quotes similar to unix style shell
        except ValueError: #no closing quotes
            print("shell: unmatched quote")
            continue
        if not words:
            continue
        if words[0].lower() == "exit":
            break
        if words[0].lower() == "pwd":
            print(os.getcwd()) #returns absolute path of folder the shell is currently in, string
            continue
        if words[0].lower() == "cd":
            if len(words) > 2:
                print("cd: too many arguments")
                continue
            target = words[1] if len(words) == 2 else "~"
            target = os.path.expanduser(target)
            try:
                os.chdir(target)
            except OSError as e:
                print(f"cd: {target}: {e.strerror}") #catches errors like folder DNE or lack of perm
            continue
        if words[0].lower() == "trace":
            if len(words) == 2 and words[1] in ("on", "off"):
                trace = (words[1] == "on")
                print(f"trace {words[1]}")
            else:
                print("usage: trace on/off")
            continue
        
        parsed = parse_redirects(words)
        if parsed is None: 
            continue
        cmd, infile, outfile, append = parsed
        run_command(cmd, trace, infile, outfile, append)

if __name__=="__main__":
    main()