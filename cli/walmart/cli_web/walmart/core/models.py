"""Data models for cli-web-walmart."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PriceInfo:
    line_price: str = ""        # "$17.88"
    unit_price: str = ""        # "$2.10/oz"
    was_price: str = ""         # "$19.99" (original, when on sale)
    savings: str = ""           # "$2.11"

    @classmethod
    def from_dict(cls, d: dict) -> "PriceInfo":
        if not d:
            return cls()

        def _str(v) -> str:
            """Extract priceString from a price object or return as-is if string."""
            if isinstance(v, dict):
                return v.get("priceString", "") or ""
            return str(v) if v else ""

        # Product detail pages use currentPrice.priceString
        current = d.get("currentPrice") or {}
        line = _str(d.get("linePrice") or current)
        unit = _str(d.get("unitPrice"))
        was = _str(d.get("wasPrice"))
        savings = _str(d.get("savings"))
        return cls(
            line_price=line,
            unit_price=unit,
            was_price=was,
            savings=savings,
        )

    def to_dict(self) -> dict:
        return {
            "line_price": self.line_price,
            "unit_price": self.unit_price,
            "was_price": self.was_price,
            "savings": self.savings,
        }


@dataclass
class SearchItem:
    """A product from a search results page."""
    item_id: str
    name: str
    brand: str = ""
    price: PriceInfo = field(default_factory=PriceInfo)
    rating: Optional[float] = None
    num_reviews: Optional[int] = None
    url: str = ""
    availability: str = ""
    seller: str = ""
    is_sponsored: bool = False
    thumbnail_url: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "SearchItem":
        price = PriceInfo.from_dict(d.get("priceInfo") or {})
        avail_v2 = d.get("availabilityStatusV2") or {}
        avail = avail_v2.get("display", "") if avail_v2 else d.get("availabilityStatusDisplayValue", "")
        image = d.get("imageInfo") or {}
        return cls(
            item_id=str(d.get("usItemId", "")),
            name=d.get("name", ""),
            brand=d.get("brand", "") or "",
            price=price,
            rating=d.get("averageRating"),
            num_reviews=d.get("numberOfReviews"),
            url=d.get("canonicalUrl", ""),
            availability=avail,
            seller=d.get("sellerName", "Walmart"),
            is_sponsored=bool(d.get("isSponsoredFlag") or d.get("sponsoredProduct")),
            thumbnail_url=image.get("thumbnailUrl", "") if image else "",
        )

    def to_dict(self) -> dict:
        full_url = self.url if self.url.startswith("http") else f"https://www.walmart.com{self.url}"
        return {
            "item_id": self.item_id,
            "name": self.name,
            "brand": self.brand,
            "price": self.price.line_price,
            "unit_price": self.price.unit_price,
            "was_price": self.price.was_price,
            "savings": self.price.savings,
            "rating": self.rating,
            "num_reviews": self.num_reviews,
            "url": full_url,
            "availability": self.availability,
            "seller": self.seller,
            "is_sponsored": self.is_sponsored,
            "thumbnail_url": self.thumbnail_url,
        }


@dataclass
class SearchResults:
    """Results from a product search."""
    query: str
    total_count: int
    page: int
    items: list[SearchItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "total_count": self.total_count,
            "page": self.page,
            "item_count": len(self.items),
            "items": [i.to_dict() for i in self.items],
        }


@dataclass
class ProductDetail:
    """Full product detail page data."""
    item_id: str
    name: str
    brand: str = ""
    price: PriceInfo = field(default_factory=PriceInfo)
    rating: Optional[float] = None
    num_reviews: Optional[int] = None
    short_description: str = ""
    long_description: str = ""
    seller: str = ""
    url: str = ""
    images: list[str] = field(default_factory=list)
    specifications: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "ProductDetail":
        price = PriceInfo.from_dict(d.get("priceInfo") or {})
        brand = d.get("brand") or ""
        if isinstance(brand, dict):
            brand = brand.get("name", "")
        images = []
        for img in d.get("images", []) or []:
            if isinstance(img, dict) and img.get("url"):
                images.append(img["url"])
        specs = []
        for spec in d.get("specifications", []) or []:
            if isinstance(spec, dict):
                specs.append({
                    "name": spec.get("name", ""),
                    "value": spec.get("value", ""),
                })
        return cls(
            item_id=str(d.get("usItemId", "")),
            name=d.get("name", ""),
            brand=brand,
            price=price,
            rating=d.get("averageRating"),
            num_reviews=d.get("numberOfReviews"),
            short_description=(d.get("shortDescription") or "").replace("<ul>", "").replace("</ul>", "").replace("<li>", "- ").replace("</li>", "\n").strip(),
            long_description=(d.get("longDescription") or "").replace("<p>", "").replace("</p>", "\n").strip()[:1000],
            seller=d.get("sellerName", "Walmart"),
            url=d.get("canonicalUrl", ""),
            images=images[:5],
            specifications=specs[:20],
        )

    def to_dict(self) -> dict:
        full_url = self.url if self.url.startswith("http") else f"https://www.walmart.com{self.url}"
        return {
            "item_id": self.item_id,
            "name": self.name,
            "brand": self.brand,
            "price": self.price.line_price,
            "unit_price": self.price.unit_price,
            "was_price": self.price.was_price,
            "savings": self.price.savings,
            "rating": self.rating,
            "num_reviews": self.num_reviews,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "seller": self.seller,
            "url": full_url,
            "images": self.images,
            "specifications": self.specifications,
        }
