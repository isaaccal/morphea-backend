from sqlalchemy.orm import Session
from models import Subscription, CreditTransaction, User

def ensure_subscription(db: Session, user: User) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).one_or_none()
    if not sub:
        sub = Subscription(user_id=user.id, plan_name="gratis", dreams_allowed=1, dreams_used=0)
        db.add(sub)
        db.flush()
    return sub

def add_credits(db: Session, user: User, credits: int) -> Subscription:
    sub = ensure_subscription(db, user)
    sub.dreams_allowed = (sub.dreams_allowed or 0) + int(credits)
    db.flush()
    return sub

def assign_pending_credits(db: Session, user: User) -> int:
    """
    Vincula compras hechas por email antes de que el usuario existiera.
    """
    pending = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.email == user.email, CreditTransaction.user_id.is_(None))
        .all()
    )
    if not pending:
        return 0
    total = sum(t.credits for t in pending)
    sub = ensure_subscription(db, user)
    for tx in pending:
        tx.user_id = user.id
    sub.dreams_allowed = (sub.dreams_allowed or 0) + total
    db.flush()
    return total

def consume_one_credit(db: Session, user: User) -> None:
    sub = ensure_subscription(db, user)
    remaining = (sub.dreams_allowed or 0) - (sub.dreams_used or 0)
    if remaining <= 0:
        raise ValueError("Sin créditos disponibles.")
    sub.dreams_used = (sub.dreams_used or 0) + 1
    db.flush()
