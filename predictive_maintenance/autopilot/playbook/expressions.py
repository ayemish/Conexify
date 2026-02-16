"""
Expression Language Evaluator

Implements a tiny expression grammar for playbook triggers, preconditions, and verifications.

Supported operations:
- Comparisons: > >= < <= == !=
- Functions: avg(point, window), slope(point, window), in_band(value, lo, hi)
- Predicates: is_valid(point), is_override_active(asset)
- Policy references: policy.max_setpoint_delta, policy.store_hours
- Logical: and, or, not
- Arithmetic: + - * /
"""

import re
import operator
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union
import math


class ExpressionError(Exception):
    """Raised when expression evaluation fails"""
    pass


@dataclass
class EvalContext:
    """Context for expression evaluation"""
    points: Dict[str, float] = None  # point_id -> current value
    point_history: Dict[str, List[float]] = None  # point_id -> historical values
    asset_id: str = ""
    regime: str = ""
    policy: Dict[str, Any] = None
    overrides: Dict[str, bool] = None  # point_id -> is_override_active
    
    def __post_init__(self):
        self.points = self.points or {}
        self.point_history = self.point_history or {}
        self.policy = self.policy or {}
        self.overrides = self.overrides or {}


class ExpressionEvaluator:
    """
    Evaluates playbook expressions against runtime context.
    
    Expression grammar (simplified):
    
    expr := comparison | function_call | predicate | policy_ref | logical_expr
    comparison := value comparator value
    comparator := '>' | '>=' | '<' | '<=' | '==' | '!='
    function_call := function_name '(' args ')'
    predicate := predicate_name '(' args ')'
    policy_ref := 'policy.' identifier
    logical_expr := expr ('and' | 'or') expr | 'not' expr
    value := number | point_ref | function_call
    point_ref := identifier
    """
    
    # Comparison operators
    OPERATORS = {
        '>': operator.gt,
        '>=': operator.ge,
        '<': operator.lt,
        '<=': operator.le,
        '==': operator.eq,
        '!=': operator.ne,
    }
    
    # Built-in functions
    FUNCTIONS = {}
    
    def __init__(self):
        self._register_functions()
    
    def _register_functions(self):
        """Register built-in functions"""
        self.FUNCTIONS = {
            'avg': self._fn_avg,
            'slope': self._fn_slope,
            'in_band': self._fn_in_band,
            'is_valid': self._fn_is_valid,
            'is_override_active': self._fn_is_override_active,
            'abs': self._fn_abs,
            'min': self._fn_min,
            'max': self._fn_max,
            'delta': self._fn_delta,
            'rate_of_change': self._fn_rate_of_change,
            'within_threshold': self._fn_within_threshold,
        }
    
    def evaluate(self, expr: str, context: EvalContext) -> Any:
        """
        Evaluate an expression in the given context.
        
        Args:
            expr: Expression string to evaluate
            context: Evaluation context with point values, policy, etc.
            
        Returns:
            Evaluation result (bool, float, or other)
            
        Raises:
            ExpressionError: If evaluation fails
        """
        try:
            expr = expr.strip()
            
            # Handle empty expression
            if not expr:
                return True
            
            # Handle logical operators (and, or, not)
            result = self._evaluate_logical(expr, context)
            return result
            
        except ExpressionError:
            raise
        except Exception as e:
            raise ExpressionError(f"Failed to evaluate expression '{expr}': {e}")
    
    def _evaluate_logical(self, expr: str, context: EvalContext) -> Any:
        """Evaluate logical expressions (and, or, not)"""
        expr = expr.strip()
        
        # Handle parentheses
        if expr.startswith('(') and expr.endswith(')'):
            # Check if these are matching parens
            depth = 0
            for i, c in enumerate(expr):
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                if depth == 0 and i < len(expr) - 1:
                    break
            else:
                # The outer parens match
                return self._evaluate_logical(expr[1:-1], context)
        
        # Handle 'not' operator
        if expr.lower().startswith('not '):
            inner = expr[4:].strip()
            return not self._evaluate_logical(inner, context)
        
        # Handle 'or' operator (lowest precedence)
        or_parts = self._split_logical(expr, ' or ')
        if len(or_parts) > 1:
            return any(self._evaluate_logical(p, context) for p in or_parts)
        
        # Handle 'and' operator
        and_parts = self._split_logical(expr, ' and ')
        if len(and_parts) > 1:
            return all(self._evaluate_logical(p, context) for p in and_parts)
        
        # Evaluate as comparison or function
        return self._evaluate_comparison(expr, context)
    
    def _split_logical(self, expr: str, sep: str) -> List[str]:
        """Split expression by logical operator, respecting parentheses"""
        parts = []
        depth = 0
        current = ""
        i = 0
        
        while i < len(expr):
            c = expr[i]
            if c == '(':
                depth += 1
                current += c
            elif c == ')':
                depth -= 1
                current += c
            elif depth == 0 and expr[i:i+len(sep)].lower() == sep.lower():
                if current.strip():
                    parts.append(current.strip())
                current = ""
                i += len(sep) - 1
            else:
                current += c
            i += 1
        
        if current.strip():
            parts.append(current.strip())
        
        return parts if len(parts) > 1 else [expr]
    
    def _evaluate_comparison(self, expr: str, context: EvalContext) -> Any:
        """Evaluate comparison expressions"""
        # Try to match comparison operators
        for op_str, op_fn in sorted(self.OPERATORS.items(), key=lambda x: -len(x[0])):
            # Find operator not inside parentheses
            depth = 0
            for i in range(len(expr)):
                if expr[i] == '(':
                    depth += 1
                elif expr[i] == ')':
                    depth -= 1
                elif depth == 0 and expr[i:i+len(op_str)] == op_str:
                    left = expr[:i].strip()
                    right = expr[i+len(op_str):].strip()
                    left_val = self._evaluate_value(left, context)
                    right_val = self._evaluate_value(right, context)
                    return op_fn(left_val, right_val)
        
        # No comparison operator found, evaluate as value/function
        return self._evaluate_value(expr, context)
    
    def _evaluate_value(self, expr: str, context: EvalContext) -> Any:
        """Evaluate a value expression (number, point, function call, policy ref)"""
        expr = expr.strip()
        
        # Handle parentheses
        if expr.startswith('(') and expr.endswith(')'):
            return self._evaluate_value(expr[1:-1], context)
        
        # Try to parse as number
        try:
            if '.' in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            pass
        
        # Handle boolean literals
        if expr.lower() == 'true':
            return True
        if expr.lower() == 'false':
            return False
        
        # Handle policy references (policy.xxx)
        if expr.startswith('policy.'):
            key = expr[7:]
            if key in context.policy:
                return context.policy[key]
            raise ExpressionError(f"Unknown policy key: {key}")
        
        # Handle function calls
        match = re.match(r'^(\w+)\s*\((.*)\)$', expr, re.DOTALL)
        if match:
            fn_name = match.group(1)
            args_str = match.group(2)
            return self._evaluate_function(fn_name, args_str, context)
        
        # Handle arithmetic expressions
        for op_char, op_fn in [('+', operator.add), ('-', operator.sub), 
                                ('*', operator.mul), ('/', operator.truediv)]:
            depth = 0
            for i in range(len(expr) - 1, -1, -1):
                if expr[i] == ')':
                    depth += 1
                elif expr[i] == '(':
                    depth -= 1
                elif depth == 0 and expr[i] == op_char:
                    left = expr[:i].strip()
                    right = expr[i+1:].strip()
                    if left and right:
                        return op_fn(
                            self._evaluate_value(left, context),
                            self._evaluate_value(right, context)
                        )
        
        # Assume it's a point reference
        if expr in context.points:
            return context.points[expr]
        
        # Check if it's a valid identifier that doesn't exist
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', expr):
            raise ExpressionError(f"Unknown point or variable: {expr}")
        
        raise ExpressionError(f"Cannot evaluate: {expr}")
    
    def _evaluate_function(self, fn_name: str, args_str: str, context: EvalContext) -> Any:
        """Evaluate a function call"""
        if fn_name not in self.FUNCTIONS:
            raise ExpressionError(f"Unknown function: {fn_name}")
        
        # Parse arguments
        args = self._parse_args(args_str, context)
        
        # Call function
        return self.FUNCTIONS[fn_name](args, context)
    
    def _parse_args(self, args_str: str, context: EvalContext) -> List[Any]:
        """Parse function arguments"""
        args = []
        current = ""
        depth = 0
        
        for c in args_str:
            if c == '(':
                depth += 1
                current += c
            elif c == ')':
                depth -= 1
                current += c
            elif c == ',' and depth == 0:
                if current.strip():
                    args.append(self._evaluate_value(current.strip(), context))
                current = ""
            else:
                current += c
        
        if current.strip():
            args.append(self._evaluate_value(current.strip(), context))
        
        return args
    
    # Built-in functions
    
    def _fn_avg(self, args: List[Any], context: EvalContext) -> float:
        """Calculate average of a point over a window"""
        if len(args) < 1:
            raise ExpressionError("avg() requires at least 1 argument")
        
        point_id = args[0] if isinstance(args[0], str) else str(args[0])
        
        if point_id in context.point_history:
            values = context.point_history[point_id]
            if values:
                return sum(values) / len(values)
        
        # Fall back to current value
        if point_id in context.points:
            return context.points[point_id]
        
        raise ExpressionError(f"No data for point: {point_id}")
    
    def _fn_slope(self, args: List[Any], context: EvalContext) -> float:
        """Calculate slope (rate of change) of a point"""
        if len(args) < 1:
            raise ExpressionError("slope() requires at least 1 argument")
        
        point_id = args[0] if isinstance(args[0], str) else str(args[0])
        
        if point_id in context.point_history:
            values = context.point_history[point_id]
            if len(values) >= 2:
                # Simple linear regression slope
                n = len(values)
                x = list(range(n))
                x_mean = sum(x) / n
                y_mean = sum(values) / n
                
                numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
                denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
                
                if denominator > 0:
                    return numerator / denominator
        
        return 0.0
    
    def _fn_in_band(self, args: List[Any], context: EvalContext) -> bool:
        """Check if value is within a band [lo, hi]"""
        if len(args) < 3:
            raise ExpressionError("in_band() requires 3 arguments: value, lo, hi")
        
        value, lo, hi = args[0], args[1], args[2]
        return lo <= value <= hi
    
    def _fn_is_valid(self, args: List[Any], context: EvalContext) -> bool:
        """Check if a point has valid data"""
        if len(args) < 1:
            raise ExpressionError("is_valid() requires 1 argument")
        
        point_id = args[0] if isinstance(args[0], str) else str(args[0])
        
        if point_id not in context.points:
            return False
        
        value = context.points[point_id]
        return value is not None and not math.isnan(value) and not math.isinf(value)
    
    def _fn_is_override_active(self, args: List[Any], context: EvalContext) -> bool:
        """Check if an override is active for a point or asset"""
        if len(args) < 1:
            raise ExpressionError("is_override_active() requires 1 argument")
        
        target_id = args[0] if isinstance(args[0], str) else str(args[0])
        return context.overrides.get(target_id, False)
    
    def _fn_abs(self, args: List[Any], context: EvalContext) -> float:
        """Absolute value"""
        if len(args) < 1:
            raise ExpressionError("abs() requires 1 argument")
        return abs(args[0])
    
    def _fn_min(self, args: List[Any], context: EvalContext) -> float:
        """Minimum of values"""
        if len(args) < 1:
            raise ExpressionError("min() requires at least 1 argument")
        return min(args)
    
    def _fn_max(self, args: List[Any], context: EvalContext) -> float:
        """Maximum of values"""
        if len(args) < 1:
            raise ExpressionError("max() requires at least 1 argument")
        return max(args)
    
    def _fn_delta(self, args: List[Any], context: EvalContext) -> float:
        """Calculate delta (current - previous) for a point"""
        if len(args) < 1:
            raise ExpressionError("delta() requires 1 argument")
        
        point_id = args[0] if isinstance(args[0], str) else str(args[0])
        
        if point_id in context.point_history:
            values = context.point_history[point_id]
            if len(values) >= 2:
                return values[-1] - values[-2]
        
        return 0.0
    
    def _fn_rate_of_change(self, args: List[Any], context: EvalContext) -> float:
        """Calculate rate of change (per minute) for a point"""
        if len(args) < 1:
            raise ExpressionError("rate_of_change() requires 1 argument")
        
        point_id = args[0] if isinstance(args[0], str) else str(args[0])
        
        # Assume 1-minute intervals if not specified
        interval_minutes = args[1] if len(args) > 1 else 1
        
        if point_id in context.point_history:
            values = context.point_history[point_id]
            if len(values) >= 2:
                return (values[-1] - values[0]) / (len(values) * interval_minutes)
        
        return 0.0
    
    def _fn_within_threshold(self, args: List[Any], context: EvalContext) -> bool:
        """Check if value is within threshold of target"""
        if len(args) < 3:
            raise ExpressionError("within_threshold() requires 3 arguments: value, target, threshold")
        
        value, target, threshold = args[0], args[1], args[2]
        return abs(value - target) <= threshold


    def validate_syntax(self, expr: str) -> bool:
        """
        Validate expression syntax without evaluating.
        
        Returns:
            True if syntax is valid, False otherwise
        """
        try:
            # Check balanced parentheses
            depth = 0
            for c in expr:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                if depth < 0:
                    return False
            if depth != 0:
                return False
            
            # Check for basic syntax issues
            if '>>' in expr or '<<' in expr or '><' in expr or '<>' in expr:
                return False
            
            # Try to parse without a context (will fail on point refs but that's ok)
            # Just check structure
            return True
        except Exception:
            return False


# Convenience function for quick evaluation
def evaluate_expression(expr: str, context: EvalContext) -> Any:
    """Evaluate an expression with the given context"""
    evaluator = ExpressionEvaluator()
    return evaluator.evaluate(expr, context)
