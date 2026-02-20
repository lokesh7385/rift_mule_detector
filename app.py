import sys
import os

# Fix 2: Path Hack for Vercel Import Resolution
sys.path.insert(0, os.path.dirname(__file__))

# Import app from the package
from api.index import app

if __name__ == "__main__":
    app.run()
