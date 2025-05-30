import re
import ast
import json

def robust_param_parser(param_string):
    """More robust parameter parser"""
    params = {}
    
    # Pattern to match key=value pairs, handling arrays
    pattern = r'(\w+)=([^,\[\]]+|\[[^\]]*\])'
    matches = re.findall(pattern, param_string)
    
    for key, value in matches:
        try:
            # Try to parse as Python literal
            parsed_value = ast.literal_eval(value.strip())
            params[key] = parsed_value
        except (ValueError, SyntaxError):
            # If parsing fails, keep as string
            params[key] = value.strip()
    
    return params

# Usage examples
test_cases = [
    "a=2, b=3, c=[1,2]",
    "name=John, age=25, scores=[95,87,92]",
    "active=True, ratio=3.14, items=[1,2,3,4]"
]

for case in test_cases:
    result = robust_param_parser(case)
    print(f"Input: {case}")
    print(f"Dict: {result}")
    print(f"JSON: {json.dumps(result)}")
    print()