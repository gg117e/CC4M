import os
import sys
from datetime import datetime


class PrintStyle:
    """
    List of codes for styling output on console
    """
    reset = '\033[0m'
    bold = '\033[01m'
    disable = '\033[02m'
    underline = '\033[04m'
    reverse = '\033[07m'
    strikethrough = '\033[09m'
    invisible = '\033[08m'

    class Fg:
        """
        List of color for styling text on console
        """
        black = '\033[30m'
        red = '\033[31m'
        green = '\033[32m'
        orange = '\033[33m'
        blue = '\033[34m'
        purple = '\033[35m'
        cyan = '\033[36m'
        lightgrey = '\033[37m'
        darkgrey = '\033[90m'
        lightred = '\033[91m'
        lightgreen = '\033[92m'
        yellow = '\033[93m'
        lightblue = '\033[94m'
        pink = '\033[95m'
        lightcyan = '\033[96m'

    class Bg:
        """
        List of color for styling background on console
        """
        black = '\033[40m'
        red = '\033[41m'
        green = '\033[42m'
        orange = '\033[43m'
        blue = '\033[44m'
        purple = '\033[45m'
        cyan = '\033[46m'
        lightgrey = '\033[47m'


def printable_time() -> str:
    """
    Returns the actual time in the correct format for logging to console

    :return: actual time formatted
    """
    return datetime.now().strftime("%H:%M:%S") + '|'


def print_major_step(string: str) -> None:
    """
    Print a major step to console

    :param string: string to print
    :return: None
    """
    print(PrintStyle.bold + PrintStyle.Fg.green + printable_time() + string + PrintStyle.reset)


def print_minor_step(string: str) -> None:
    """
    Print a minor step to console

    :param string: string to print
    :return: None
    """
    print(PrintStyle.Fg.green + printable_time() + string + PrintStyle.reset)


def print_info(string: str) -> None:
    """
    Print an info to console

    :param string: string to print
    :return: None
    """
    print(PrintStyle.Fg.purple + printable_time() + string + PrintStyle.reset)


def print_warning(string: str) -> None:
    """
    Print a warning to console

    :param string: string to print
    :return: None
    """
    print(PrintStyle.Fg.orange + printable_time() + string + PrintStyle.reset)


def print_error(string: str) -> None:
    """
    Print an error to console

    :param string: string to print
    :return: None
    """
    print(PrintStyle.Fg.red + printable_time() + string + PrintStyle.reset)


def print_progress(string: str) -> None:
    """
    Print a progress to console

    :param string: string to print
    :return: None
    """
    print(PrintStyle.bold + PrintStyle.Fg.cyan + printable_time() + string + PrintStyle.reset)


def print_appendable(string: str) -> None:
    """
    Print a string without new line at the end

    :param string: string to print
    :return: None
    """
    print(string, end="", flush=True)


def block_print() -> None:
    """
    Disable the STD OUT

    :return: None
    """
    sys.stdout = open(os.devnull, 'w')


def restore_print() -> None:
    """
    Restore the STD OUT

    :return: None
    """
    sys.stdout = sys.__stdout__
