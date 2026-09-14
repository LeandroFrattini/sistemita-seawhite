from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from sqlalchemy import select

from ..auth import admin_required, hash_password
from ..database import get_db
from ..models import EventTemplate, ReportLog, Terminal, User
from ..service import CC_KEY, DEFAULT_CC, SIGNATURE_KEY, all_terminals, get_setting, set_setting, split_emails

FLAMMABLE_LIST_KEY = "flammable_list_emails"
from ..templating import templates

router = APIRouter(prefix="/admin")


ADMIN_TABS = {"usuarios", "terminales", "wordings", "mails", "clientes", "registros"}


@router.get("", response_class=HTMLResponse)
def admin_home(
    request: Request, tab: str = "usuarios",
    db: Session = Depends(get_db), user: User = Depends(admin_required),
):
    tab = tab if tab in ADMIN_TABS else "usuarios"
    users = db.query(User).order_by(User.username).all()
    logs = db.query(ReportLog).order_by(ReportLog.generated_at.desc()).limit(50).all()
    events = db.scalars(select(EventTemplate).order_by(EventTemplate.category, EventTemplate.text))
    return templates.TemplateResponse(
        request,
        "admin/home.html",
        {
            "user": user,
            "tab": tab,
            "users": users,
            "terminals": all_terminals(db),
            "logs": logs,
            "events": list(events),
            "signature_html": get_setting(db, SIGNATURE_KEY, ""),
            "report_cc": get_setting(db, CC_KEY, DEFAULT_CC),
            "flammable_list_emails": split_emails(get_setting(db, FLAMMABLE_LIST_KEY, "")),
        },
    )


@router.post("/flammable-list")
def save_flammable_list(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    flammable_list: str = Form(""),
):
    # se suma a lo que ya habia cargado (igual que "Agregar mails" en Clientes)
    existing = split_emails(get_setting(db, FLAMMABLE_LIST_KEY, ""))
    lower = {e.lower() for e in existing}
    for e in split_emails(flammable_list):
        if e.lower() not in lower:
            existing.append(e)
            lower.add(e.lower())
    set_setting(db, FLAMMABLE_LIST_KEY, ", ".join(existing))
    return RedirectResponse("/admin?tab=mails#sec-flam", status_code=302)


@router.post("/flammable-list/mail-remove")
def remove_flammable_mail(
    email: str = "",
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
):
    target = email.strip().lower()
    remaining = [e for e in split_emails(get_setting(db, FLAMMABLE_LIST_KEY, "")) if e.lower() != target]
    set_setting(db, FLAMMABLE_LIST_KEY, ", ".join(remaining))
    return RedirectResponse("/admin?tab=mails#sec-flam", status_code=302)


@router.post("/signature")
def save_signature(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    signature_html: str = Form(""),
):
    set_setting(db, SIGNATURE_KEY, signature_html.strip())
    return RedirectResponse("/admin?tab=mails#sec-firma", status_code=302)


@router.post("/report-cc")
def save_report_cc(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    report_cc: str = Form(""),
):
    set_setting(db, CC_KEY, report_cc.strip())
    return RedirectResponse("/admin?tab=mails#sec-cc", status_code=302)


# --- Usuarios ------------------------------------------------------------- #
@router.post("/users")
def create_user(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    username: str = Form(...),
    full_name: str = Form(""),
    password: str = Form(""),
    is_admin: str = Form(""),
):
    username = username.strip()
    if username and not db.query(User).filter(User.username == username).first():
        # si no cargaste contraseña, arranca igual al usuario -- se le va a
        # pedir que la cambie en el primer login
        initial_pw = password.strip() or username
        db.add(
            User(
                username=username,
                full_name=full_name.strip(),
                password_hash=hash_password(initial_pw),
                is_admin=is_admin == "on",
                is_active=True,
                must_change_password=True,
            )
        )
        db.commit()
    return RedirectResponse("/admin?tab=usuarios", status_code=302)


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
            # resetear la clave: no se puede "ver" la vieja, pero se pone una
            # nueva y se le exige cambiarla apenas entre
            u.password_hash = hash_password(password.strip())
            u.must_change_password = True
        db.commit()
    return RedirectResponse(f"/admin?tab=usuarios#usr-{user_id}", status_code=302)


# --- Terminales --------------------------------------------------------- #
@router.post("/terminals")
def create_terminal(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    code: str = Form(...),
    name: str = Form(""),
    berth_label: str = Form(""),
    kind: str = Form("GRAIN"),
    sort_order: int = Form(100),
    exclude_from_excel: str = Form(""),
):
    db.add(
        Terminal(
            code=code.strip(),
            name=name.strip(),
            berth_label=berth_label.strip(),
            kind="FLAMMABLE" if kind.upper() == "FLAMMABLE" else "GRAIN",
            sort_order=sort_order,
            active=True,
            exclude_from_excel=exclude_from_excel == "on",
        )
    )
    db.commit()
    return RedirectResponse("/admin?tab=terminales", status_code=302)


@router.post("/terminals/{terminal_id}")
def update_terminal(
    terminal_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    code: str = Form(...),
    name: str = Form(""),
    berth_label: str = Form(""),
    kind: str = Form("GRAIN"),
    sort_order: int = Form(100),
    active: str = Form(""),
    exclude_from_excel: str = Form(""),
):
    t = db.get(Terminal, terminal_id)
    if t:
        t.code = code.strip()
        t.name = name.strip()
        t.berth_label = berth_label.strip()
        t.kind = "FLAMMABLE" if kind.upper() == "FLAMMABLE" else "GRAIN"
        t.sort_order = sort_order
        t.active = active == "on"
        t.exclude_from_excel = exclude_from_excel == "on"
        db.commit()
    return RedirectResponse(f"/admin?tab=terminales#trm-{terminal_id}", status_code=302)


# --- Eventos (biblioteca) ------------------------------------------------ #
@router.post("/events")
def create_event_template(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    category: str = Form(""),
    text: str = Form(...),
):
    if text.strip():
        db.add(EventTemplate(category=category.strip().upper() or "GENERAL", text=text.strip(), active=True))
        db.commit()
    return RedirectResponse("/admin?tab=wordings#sec-events", status_code=302)


@router.post("/events/{event_id}")
def update_event_template(
    event_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
    category: str = Form(""),
    text: str = Form(...),
    active: str = Form(""),
):
    e = db.get(EventTemplate, event_id)
    if e:
        e.category = category.strip().upper() or "GENERAL"
        e.text = text.strip()
        e.active = active == "on"
        db.commit()
    return RedirectResponse("/admin?tab=wordings#sec-events", status_code=302)


@router.post("/events/{event_id}/borrar")
def delete_event_template(
    event_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required),
):
    e = db.get(EventTemplate, event_id)
    if e:
        db.delete(e)
        db.commit()
    return RedirectResponse("/admin?tab=wordings#sec-events", status_code=302)
