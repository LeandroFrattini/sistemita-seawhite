from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import admin_required, hash_password
from ..database import get_db
from ..models import ReportLog, Terminal, User
from ..service import SIGNATURE_KEY, all_terminals, get_setting, set_setting
from ..templating import templates

router = APIRouter(prefix="/admin")


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db), user: User = Depends(admin_required)):
    users = db.query(User).order_by(User.username).all()
    logs = db.query(ReportLog).order_by(ReportLog.generated_at.desc()).limit(50).all()
    return templates.TemplateResponse(
        request,
        "admin/home.html",
        {
            "user": user,
            "users": users,
            "terminals": all_terminals(db),
            "logs": logs,
            "signature_html": get_setting(db, SIGNATURE_KEY, ""),
        },
    )


@router.post("/signature")
def save_signature(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    signature_html: str = Form(""),
):
    set_setting(db, SIGNATURE_KEY, signature_html.strip())
    return RedirectResponse("/admin", status_code=302)


# --- Usuarios ------------------------------------------------------------- #
@router.post("/users")
def create_user(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    username: str = Form(...),
    full_name: str = Form(""),
    password: str = Form(...),
    is_admin: str = Form(""),
):
    username = username.strip()
    if username and not db.query(User).filter(User.username == username).first():
        db.add(
            User(
                username=username,
                full_name=full_name.strip(),
                password_hash=hash_password(password),
                is_admin=is_admin == "on",
                is_active=True,
            )
        )
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/users/{user_id}")
def update_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    full_name: str = Form(""),
    password: str = Form(""),
    is_admin: str = Form(""),
    is_active: str = Form(""),
):
    u = db.get(User, user_id)
    if u:
        u.full_name = full_name.strip()
        u.is_admin = is_admin == "on"
        u.is_active = is_active == "on"
        if password.strip():
            u.password_hash = hash_password(password.strip())
        db.commit()
    return RedirectResponse("/admin", status_code=302)


# --- Terminales --------------------------------------------------------- #
@router.post("/terminals")
def create_terminal(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    code: str = Form(...),
    name: str = Form(""),
    berth_label: str = Form(""),
    sort_order: int = Form(100),
):
    db.add(
        Terminal(
            code=code.strip(),
            name=name.strip(),
            berth_label=berth_label.strip(),
            sort_order=sort_order,
            active=True,
        )
    )
    db.commit()
    return RedirectResponse("/admin", status_code=302)


@router.post("/terminals/{terminal_id}")
def update_terminal(
    terminal_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    code: str = Form(...),
    name: str = Form(""),
    berth_label: str = Form(""),
    sort_order: int = Form(100),
    active: str = Form(""),
):
    t = db.get(Terminal, terminal_id)
    if t:
        t.code = code.strip()
        t.name = name.strip()
        t.berth_label = berth_label.strip()
        t.sort_order = sort_order
        t.active = active == "on"
        db.commit()
    return RedirectResponse("/admin", status_code=302)
