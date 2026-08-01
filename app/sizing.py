from dataclasses import dataclass


@dataclass(frozen=True)
class ShoeSize:
    eu: float
    cm: float
    us: float


# Nike men's footwear chart is used as a normalized marketplace baseline.
SHOE_SIZES = (
    ShoeSize(35.5, 22.5, 3.5),
    ShoeSize(36, 23, 4),
    ShoeSize(36.5, 23.5, 4.5),
    ShoeSize(37.5, 23.5, 5),
    ShoeSize(38, 24, 5.5),
    ShoeSize(38.5, 24, 6),
    ShoeSize(39, 24.5, 6.5),
    ShoeSize(40, 25, 7),
    ShoeSize(40.5, 25.5, 7.5),
    ShoeSize(41, 26, 8),
    ShoeSize(42, 26.5, 8.5),
    ShoeSize(42.5, 27, 9),
    ShoeSize(43, 27.5, 9.5),
    ShoeSize(44, 28, 10),
    ShoeSize(44.5, 28.5, 10.5),
    ShoeSize(45, 29, 11),
    ShoeSize(45.5, 29.5, 11.5),
    ShoeSize(46, 30, 12),
    ShoeSize(47, 30.5, 12.5),
    ShoeSize(47.5, 31, 13),
    ShoeSize(48, 31.5, 13.5),
    ShoeSize(48.5, 32, 14),
    ShoeSize(49, 32.5, 14.5),
    ShoeSize(49.5, 33, 15),
    ShoeSize(50, 33.5, 15.5),
)


def shoe_size_options(eu_input: str | None) -> tuple[ShoeSize, ...]:
    if not eu_input:
        return ()
    try:
        requested = float(eu_input.strip().replace(",", "."))
    except ValueError:
        return ()
    start = next((index for index, size in enumerate(SHOE_SIZES) if size.eu == requested), None)
    if start is None:
        return ()
    return SHOE_SIZES[start : start + 2]


def format_size(value: float) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)
