__all__ = ['ProductGrid', 'StatsPanel']


def __getattr__(name):
    if name == 'ProductGrid':
        from .product_grid import ProductGrid
        return ProductGrid
    if name == 'StatsPanel':
        from .stats_panel import StatsPanel
        return StatsPanel
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
