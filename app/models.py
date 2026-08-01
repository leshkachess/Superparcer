from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, model_validator


class ClothingType(StrEnum):
    T_SHIRT = "Футболка"
    HOODIE = "Худи"
    JACKET = "Куртка"
    TROUSERS = "Брюки"
    JEANS = "Джинсы"
    SHOES = "Обувь"
    ACCESSORY = "Аксессуар"


class SearchFilters(BaseModel):
    brand: str | None = Field(default=None, max_length=80)
    size: str | None = Field(default=None, max_length=30)
    price_from: int | None = Field(default=None, ge=0)
    price_to: int | None = Field(default=None, ge=0)
    clothing_type: ClothingType | None = None
    sources: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_price_range(self) -> "SearchFilters":
        if self.price_from is not None and self.price_to is not None:
            if self.price_from > self.price_to:
                raise ValueError("Минимальная цена не может быть больше максимальной")
        return self


class Product(BaseModel):
    source: str
    title: str
    brand: str | None = None
    sizes: list[str] = []
    price: int
    currency: str = "RUB"
    clothing_type: ClothingType | None = None
    url: HttpUrl
    image_url: HttpUrl | None = None


class SearchResponse(BaseModel):
    products: list[Product]
    errors: dict[str, str] = {}
    source_links: list["SourceSearchLink"] = []


class SourceSearchLink(BaseModel):
    source: str
    url: HttpUrl
    note: str


class SourceInfo(BaseModel):
    id: str
    name: str
