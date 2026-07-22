import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "showroom.db"
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="ShowroomAI")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS company (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            assistant_name TEXT NOT NULL,
            greeting TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            specs TEXT NOT NULL,
            image_url TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS managers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            speciality TEXT NOT NULL,
            available INTEGER NOT NULL DEFAULT 1,
            assigned_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_name TEXT,
            requirement TEXT,
            budget TEXT,
            selected_product TEXT,
            manager_name TEXT,
            summary TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO company (id, name, assistant_name, greeting) VALUES (1, ?, ?, ?)",
        ("Aurum Motors", "Ava", "Hi, welcome to Aurum Motors. How can I help you today?"),
    )
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        products = [
            ("Volvo XC90 Recharge", 58900, "SUV", "Premium seven-seat plug-in hybrid family SUV.", json.dumps({"fuel":"Plug-in hybrid","seats":7,"drive":"AWD"}), "https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=1200&q=80"),
            ("BMW X5 xDrive50e", 64900, "SUV", "Luxury performance SUV with hybrid efficiency.", json.dumps({"fuel":"Plug-in hybrid","seats":5,"drive":"AWD"}), "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1200&q=80"),
            ("Audi Q7", 61500, "SUV", "Spacious premium SUV suitable for family and business use.", json.dumps({"fuel":"Diesel","seats":7,"drive":"Quattro"}), "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=1200&q=80")
        ]
        conn.executemany("INSERT INTO products (name,price,category,description,specs,image_url) VALUES (?,?,?,?,?,?)", products)
    if conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO managers (name,speciality,available) VALUES (?,?,1)",
            [("Erika", "SUV and hybrid vehicles"), ("Tomas", "Premium and performance vehicles")],
        )
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def showroom(request: Request):
    conn = get_db()
    company = dict(conn.execute("SELECT * FROM company WHERE id=1").fetchone())
    products = [dict(row) for row in conn.execute("SELECT * FROM products ORDER BY id")]
    conn.close()
    for product in products:
        product["specs"] = json.loads(product["specs"])
    return templates.TemplateResponse("showroom.html", {"request": request, "company": company, "products": products})


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    conn = get_db()
    company = dict(conn.execute("SELECT * FROM company WHERE id=1").fetchone())
    products = [dict(row) for row in conn.execute("SELECT * FROM products ORDER BY id DESC")]
    managers = [dict(row) for row in conn.execute("SELECT * FROM managers ORDER BY id")]
    leads = [dict(row) for row in conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 50")]
    conn.close()
    return templates.TemplateResponse("admin.html", {"request": request, "company": company, "products": products, "managers": managers, "leads": leads})


@app.post("/admin/company")
def update_company(name: str = Form(...), assistant_name: str = Form(...), greeting: str = Form(...)):
    conn = get_db()
    conn.execute("UPDATE company SET name=?, assistant_name=?, greeting=? WHERE id=1", (name, assistant_name, greeting))
    conn.commit(); conn.close()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/products")
def add_product(name: str = Form(...), price: float = Form(...), category: str = Form(...), description: str = Form(...), specs: str = Form(...), image_url: str = Form("")):
    parsed_specs = {}
    for line in specs.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            parsed_specs[key.strip()] = value.strip()
    conn = get_db()
    conn.execute("INSERT INTO products (name,price,category,description,specs,image_url) VALUES (?,?,?,?,?,?)", (name,price,category,description,json.dumps(parsed_specs),image_url))
    conn.commit(); conn.close()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/managers")
def add_manager(name: str = Form(...), speciality: str = Form(...)):
    conn = get_db(); conn.execute("INSERT INTO managers (name,speciality,available) VALUES (?,?,1)", (name,speciality)); conn.commit(); conn.close()
    return RedirectResponse("/admin", status_code=303)


def assign_manager(conn: sqlite3.Connection) -> str:
    manager = conn.execute("SELECT * FROM managers WHERE available=1 ORDER BY assigned_count ASC, id ASC LIMIT 1").fetchone()
    if not manager:
        return "a sales specialist"
    conn.execute("UPDATE managers SET assigned_count=assigned_count+1 WHERE id=?", (manager["id"],))
    return manager["name"]


@app.post("/api/chat")
async def chat(payload: dict[str, Any]):
    message = str(payload.get("message", "")).strip()
    history = payload.get("history", [])[-10:]
    known = payload.get("lead", {})
    conn = get_db()
    company = dict(conn.execute("SELECT * FROM company WHERE id=1").fetchone())
    products = [dict(row) for row in conn.execute("SELECT * FROM products ORDER BY id")]
    for p in products:
        p["specs"] = json.loads(p["specs"])

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        conn.close()
        return JSONResponse({"error":"OPENAI_API_KEY is missing. Add it to .env."}, status_code=500)

    system = f"""You are {company['assistant_name']}, a warm, natural showroom sales assistant for {company['name']}.
Speak briefly, like a skilled human receptionist. Do not sound like a form or chatbot.
Your goals: understand the visitor's requirement, ask their name only if not naturally provided, learn an approximate budget when relevant, ask only business-relevant missing questions, and recommend only products in the supplied catalogue.
Show one product at a time. The visitor may say next, previous, go back, compare, tell me more, or choose this one.
Never invent products, prices, specifications, discounts, or availability.
When enough information is collected and the visitor shows interest, conclude by saying a sales manager will join shortly.
Return strict JSON with keys: reply (string), visitor_name (string or null), requirement (string or null), budget (string or null), product_id (integer or null), handoff (boolean).
Catalogue: {json.dumps(products)}
Known lead data: {json.dumps(known)}
"""
    client = OpenAI(api_key=api_key)
    input_messages = [{"role":"system","content":system}]
    for item in history:
        if item.get("role") in {"user","assistant"}:
            input_messages.append({"role":item["role"],"content":str(item.get("content", ""))})
    input_messages.append({"role":"user","content":message})
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=input_messages,
            text={"format":{"type":"json_object"}},
        )
        data = json.loads(response.output_text)
    except Exception as exc:
        conn.close()
        return JSONResponse({"error":f"OpenAI request failed: {exc}"}, status_code=500)

    manager_name = None
    if data.get("handoff"):
        manager_name = assign_manager(conn)
        selected = next((p["name"] for p in products if p["id"] == data.get("product_id")), "")
        summary = f"{data.get('visitor_name') or 'Visitor'} | {data.get('requirement') or ''} | Budget: {data.get('budget') or 'not stated'} | Product: {selected or 'not selected'}"
        conn.execute("INSERT INTO leads (visitor_name,requirement,budget,selected_product,manager_name,summary) VALUES (?,?,?,?,?,?)", (data.get("visitor_name"),data.get("requirement"),data.get("budget"),selected,manager_name,summary))
        conn.commit()
        data["reply"] = data.get("reply", "") + f" {manager_name} has been assigned and will join you shortly."
    conn.close()
    data["manager_name"] = manager_name
    return data
