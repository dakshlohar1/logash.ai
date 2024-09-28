import subprocess
import datetime
import os
import sys
import signal
import argparse
import json
from pathlib import Path
import select
import pexpect
import pty
import glob
import fcntl
import termios
import readline


class BashSessionLogger:
    def __init__(self, output_dir, text_color, bg_color):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.text_color = text_color
        self.bg_color = bg_color
        self.session_file = None
        self.start_time = None
        self.end_time = None

    def start_session(self, resume_file=None):
        if resume_file:
            self.session_file = resume_file
            self.start_time = datetime.datetime.fromtimestamp(os.path.getctime(resume_file))
            print(f"Resuming session from {self.session_file}")
        else:
            self.start_time = datetime.datetime.now()
            self.session_file = self.output_dir / f"{self.start_time.strftime('%Y%m%d-%H%M%S')}-session_start.sh"

        # Set terminal colors
        os.system(f'tput setaf {self.text_color}')

        print(f"Session started. Logging to {self.session_file}")

    def end_session(self):
        self.end_time = datetime.datetime.now()
        new_filename = self.output_dir / f"{self.start_time.strftime('%Y%m%d-%H%M%S')}-{self.end_time.strftime('%H%M%S')}.sh"
        os.rename(self.session_file, new_filename)

        # Reset terminal colors
        os.system('tput sgr0')

        print(f"Session ended. Log saved as {new_filename}")

    def execute_command(self, command):
        try:
            #  use pexpect to spwan command
            child  = pexpect.spawn(command, encoding='utf-8')

            #  set up file descriptor for reading
            fd = child.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            output = ""
            while True:
                try:
                    if not child.isalive():
                        break
                    r, w, e = select.select([child, sys.stdin], [], [],.1)
                    if child in r:
                        try:
                            chunk = child.read_nonblocking(1024, timeout=0)
                            print(chunk, end='',flush=True)
                            output += chunk
                        except pexpect.exceptions.TIMEOUT:
                            pass
                        except pexpect.exceptions.EOF:
                            break
                except KeyboardInterrupt:
                    child.sendintr()
                    output += "^C\n"
                    print("^C")
                    break
            output += child.read()
            # print(output, end='',flush=True)
            return output
        except Exception as e:
            return str(e)

    def log_command(self, command, output):
        with open(self.session_file, 'a') as f:
            f.write(f"{command}\n")
            f.write(f"# Output:\n# {output.replace(chr(10), chr(10)+'# ')}\n\n")

    def run(self):
        def signal_handler(sig, frame):
            self.end_session()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        while True:
            try:
                command  = self.get_command()
                if command.lower() in ['exit', 'quit']:
                    break

                output = self.execute_command(command)
                self.log_command(command, output)

            except EOFError:
                break

        self.end_session()

    def get_command(self):
        command = ''
        while True:
            char  = sys.stdin.read(1)
            # enter key (\n and \r)
            if char in ['\n', '\r']:
                break
            # backspace key
            elif char == '\x7f':
                if len(command) > 0:
                    command = command[:-1]
                    sys.stdout.write('\b \b')
            # tab key
            elif char == '\t':
                pass
            elif char == '\x03':
                raise EOFError
            # arrow keys
            elif char == '\x1b':
                next1, next2 = sys.stdin.read(2)
                if next1 == '[':
                    if next2 == 'A':
                        pass
                    elif next2 == 'B':
                        pass
                    #  right arrow
                    elif next2 == 'C':
                        # move cursor to the right
                        sys.stdout.write('\x1b[C')
                        sys.stdout.flush()
                    # left arrow
                    elif next2 == 'D':
                        # move cursor to the left
                        sys.stdout.write('\x1b[D')
                        sys.stdout.flush()
            else:
                command += char
                sys.stdout.flush()
        return command

    @staticmethod
    def review_sessions(directory):
        directory = Path(directory)
        session_files = sorted(directory.glob("*.sh"), key=os.path.getmtime, reverse=True)

        for i, file in enumerate(session_files):
            print(f"{i+1}. {file.name}")

        choice = input("Enter the number of the session to view (or 'q' to quit): ")
        if choice.lower() == 'q':
            return

        try:
            choice = int(choice) - 1
            if 0 <= choice < len(session_files):
                with open(session_files[choice], 'r') as f:
                    print(f.read())
            else:
                print("Invalid choice.")
        except ValueError:
            print("Invalid input.")

    @staticmethod
    def search_sessions(directory, keyword):
        directory = Path(directory)
        session_files = directory.glob("*.sh")

        for file in session_files:
            with open(file, 'r') as f:
                content = f.read()
                if keyword in content:
                    print(f"Found in {file.name}:")
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if keyword in line:
                            print(f"  Line {i+1}: {line}")
                    print()

def main():
    parser = argparse.ArgumentParser(description="Bash Session Logger")
    parser.add_argument("--output", default="./sessions", help="Output directory for session logs")
    parser.add_argument("--text-color", type=int, default=2, help="Text color (ANSI color code)")
    parser.add_argument("--bg-color", type=int, default=8, help="Background color (ANSI color code)")
    parser.add_argument("--resume", help="Resume a specific session file")
    parser.add_argument("--review", action="store_true", help="Review past sessions")
    parser.add_argument("--search", help="Search keyword in past sessions")

    args = parser.parse_args()

    if args.review:
        BashSessionLogger.review_sessions(args.output)
    elif args.search:
        BashSessionLogger.search_sessions(args.output, args.search)
    else:
        logger = BashSessionLogger(args.output, args.text_color, args.bg_color)
        logger.start_session(args.resume)
        logger.run()

if __name__ == "__main__":
    main()
