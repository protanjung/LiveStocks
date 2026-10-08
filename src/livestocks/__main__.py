"""Command-line entry point: python -m livestocks or the livestocks script.
It delegates to livestocks.app.main, which starts the web server.
Keeping it separate leaves importing the package free of side effects.
"""

from livestocks.app import main

if __name__ == "__main__":
    main()
