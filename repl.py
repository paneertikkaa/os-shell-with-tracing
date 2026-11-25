import os
import sys
import shlex
import time
import signal
#shell lexical analysis, parses strings like the syntax rules of a unix shell

def parse_redirects(words):
    cmd = [] #actual command itself like ls/cat/etc
    infile = None #filename after < (slot 0, read file input instead of kyb)
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

def split_pipe(words): #only to split words before and after |
    stages = [[]]
    for w in words:
        if w == "|":
            stages.append([])
        else:
            stages[-1].append(w)
    return stages

def exec_child(words, infile, outfile, append):
#runs inside a forked child. never returns
    try:
        if infile is not None:
            fd = os.open(infile, os.O_RDONLY)
            os.dup2(fd, 0)
            os.close(fd)
        if outfile is not None:
                flags = os.O_WRONLY | os.O_CREAT #open for writing only, create a new file
                flags |= os.O_APPEND if append else os.O_TRUNC #if append is true it appends else rewrites
                fd = os.open(outfile, flags, 0o644)
                os.dup2(fd, 1)
                os.close(fd)
    except OSError as e:
        print(f"shell: {e.filename}: {e.strerror}", file=sys.stderr)
        os._exit(1)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        
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
            
def wait_for(pid):
#pauses parent(shell) until child terminates, and returns status code and usage only
#wait4 usually returns finished_pid, status_code, resource_usage
    try:
        _, status, usage = os.wait4(pid,0)
    except KeyboardInterrupt:
        print()
        _, status, usage = os.wait4(pid, 0)
    return status, usage

def decode_status(status, label=""):
    if os.WIFEXITED(status): #checks whether child terminated normally 
        code = os.WEXITSTATUS(status) #extracts status code 8 bits
        if code != 0: #if errors pop up
            print(f"{label}exit status {code}")
        return f"exit {code}"
    if os.WIFSIGNALED(status): #identifies if child was killed by signals
        print(f"{label} killed by signal {os.WTERMSIG(status)}")
        return f"signal {os.WTERMSIG(status)}"
    return "unknown"

def redir_text(infile, outfile, append):
    text = ""
    if infile is not None:
        text += f" in={infile}"
    if outfile is not None:
        text += f" out={outfile}{' (append)' if append else ''}"
    return text

def print_trace(words, pid, outcome, elapsed, usage, extra=""):
    print(
                f"trace: cmd={' '.join(words)} pid={pid} "
                f"ppid={os.getpid()} outcome={outcome} time={elapsed:.3f}s " ##ppid is the shells id
                f"usage={usage.ru_utime + usage.ru_stime:.4f}s{extra}",
                file=sys.stderr,
            )

def run_command(words, trace, infile=None, outfile=None, append=False):
    sys.stdout.flush() #any text in internal output buffer is written out so child doesnt inherit
    start = time.monotonic() #stopwatch starts
    pid = os.fork()

    if pid == 0: #child runs the process
        exec_child(words, infile, outfile, append)
    else: #parent runs
        status, usage = wait_for(pid)
        elapsed = time.monotonic() - start #stopwatch stopped
        outcome = decode_status(status)
        if trace:
            print_trace(words, pid, outcpme, elapsed, usage, redir_text(infile, outfile, append))

def run_pipeline(lwords, linfile, rwords, routfile, rappend, trace):
    sys.stdout.flush()
    start = time.monotonic()

    r, w = os.pipe()  #done before forking

    pid1 = os.fork()
    if pid1 == 0:
        os.dup2(w, 1) # slot 1 now feeds the pipe
        os.close(r)   # close BOTH original numbers
        os.close(w)
        exec_child(lwords, linfile, None, False)

    pid2 = os.fork()
    if pid2 == 0:
        os.dup2(r, 0) # slot 0 now reads from the pipe
        os.close(r)
        os.close(w) #otherwise this child holds its OWN write end
        exec_child(rwords, None, routfile, rappend)

    os.close(r)
    os.close(w)

    status1, usage1 = wait_for(pid1)
    t1 = time.monotonic() - start
    status2, usage2 = wait_for(pid2)
    t2 = time.monotonic() - start

    outcome1 = decode_status(status1, label=f"{lwords[0]}: ")
    outcome2 = decode_status(status2, label=f"{rwords[0]}: ")

    if trace:
        print_trace(lwords, pid1, outcome1, t1, usage1,
                    " pipe=write" + redir_text(linfile, None, False))
        print_trace(rwords, pid2, outcome2, t2, usage2,
                    " pipe=read" + redir_text(None, routfile, rappend))

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

        stages = split_pipe(words)
        if len(stages) > 2:
            print("shell: only one pipe (|) is supported")
            continue
        
        parsed = [parse_redirects(stage) for stage in stages]
        if None in parsed:       # parse_redirects already printed the error
            continue

        if len(parsed) == 1:
            cmd, infile, outfile, append = parsed[0]
            run_command(cmd, trace, infile, outfile, append)
        else:
            lcmd, lin, lout, lapp = parsed[0]
            rcmd, rin, rout, rapp = parsed[1]
            # the pipe already owns slot 1 on the left and slot 0 on the right
            if lout is not None:
                print("shell: syntax error: output of the left command is already piped")
                continue
            if rin is not None:
                print("shell: syntax error: input of the right command is already piped")
                continue
            run_pipeline(lcmd, lin, rcmd, rout, rapp, trace)

if __name__=="__main__":
    main()