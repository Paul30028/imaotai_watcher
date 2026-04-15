from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_admin
from models.models import Product
from schemas.schemas import ProductCreate, ProductUpdate, ProductOut, MessageResponse

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(account_id: int | None = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    query = db.query(Product)
    if account_id is not None:
        query = query.filter(Product.account_id == account_id)
    else:
        query = query.filter(Product.account_id == None)
    return query.all()


@router.post("", response_model=ProductOut)
def create_product(body: ProductCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    product = Product(
        account_id=body.account_id,
        item_code=body.item_code,
        item_name=body.item_name,
        enabled=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    if body.enabled is not None:
        product.enabled = body.enabled
    if body.item_name is not None:
        product.item_name = body.item_name
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", response_model=MessageResponse)
def delete_product(product_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    db.delete(product)
    db.commit()
    return MessageResponse(message="删除成功")
