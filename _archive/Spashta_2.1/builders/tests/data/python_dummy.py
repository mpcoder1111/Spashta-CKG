import os
import sys
import asyncio
from typing import List, Optional
import requests

# 1. DataModel (Literal coverage via heuristic)
query = "SELECT * FROM users"

# Fragment coverage
html_frag = "<html lang='en'><div>Hello</div></html>"

# 2. Inheritance (extends)
class BaseClass:
    """This is a test docstring for BaseClass."""
    base_var = 1
    def __init__(self):
        self.instance_var = 2

class ChildClass(BaseClass):
    pass

class UserModel:
    id: int
    name: str

# 3. Reads/Writes (reads_from, writes_to)
def variable_ops():
    x = 10
    y = x

# 4. Exception (throws_exception)
def error_func():
    raise ValueError("fail")

# 5. Async (uses_async)
async def async_helper():
    pass

async def async_func():
    await async_helper()

# 6. API, Render, Decorator
# (Decorator logic already retained as edge, removed as node usage)
def my_dec(f):
    return f

@my_dec
def decorated_func():
    pass

def view(request):
    # API Call (calls_api)
    requests.get("https://example.com")
    
    # Render (renders_template)
    # Note: 'render' is not defined, but AST parser accepts the call structure.
    # Builder heuristic should match 'render(req, template)'
    render(request, "index.html")
