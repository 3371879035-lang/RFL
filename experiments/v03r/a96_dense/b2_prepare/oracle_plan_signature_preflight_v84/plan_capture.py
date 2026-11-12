"""Test-only exact-signature recorder. No native dispatch or scientific authority."""
import inspect

def plan_capture(original, observer):
    """Keep the real unbound signature, not a synthetic __signature__ or __wrapped__."""
    params = tuple(inspect.signature(original, follow_wrapped=False).parameters)
    if params != ("self", "addresses", "targets"):
        raise TypeError(f"original unbound plan is not (self,addresses,targets): {params}")
    if not callable(observer):
        raise TypeError("observer must be callable")
    def capture(law, addresses, targets):
        delivery = targets  # local record name; the bound API remains addresses,targets
        result = original(law, addresses, delivery)
        observer(law, addresses, delivery, result)
        return result
    return capture

