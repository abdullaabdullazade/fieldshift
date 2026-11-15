"""AI agronomist chat on DeepSeek (OpenAI-compatible API) with function calling into FieldShift's real data."""
import json
import os
from datetime import date

import httpx

from . import services
from .db import connect, row, rows, tx
from .weather import WMO, forecast

API_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions"
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

SYSTEM = """You are the agronomy assistant of the Field Shift platform. You help farmers in Azerbaijan with crop
choice, climate risk, irrigation, frost/heat stress and yields. Be short and practical. Reply in the language the user
writes in (English by default).
Only quote numbers that come from the tools (NASA POWER, AzStat/stat.gov.az, SoilGrids, NASA NEX-GDDP-CMIP6, FAOSTAT,
Open-Meteo). Azerbaijan has district-level official yields; other countries have provinces with NASA climate and soil
data plus country-level FAOSTAT yields. If the
data is missing, say so plainly instead of guessing. Briefly name the source.
Yields are in centners per hectare (1 c/ha = 100 kg/ha). Today is {today}.{ctx}"""

TOOLS = [
    {"type": "function", "function": {
        "name": "rayon_profile", "description": "District profile: soil, past vs present climate (1981-90 vs "
        "2016-25), main crops, number of farmers, buyer rating and active fires in the last 24 h (NASA FIRMS) and the latest NASA satellite conditions (MODIS NDVI, "
        "SMAP soil moisture, GPM IMERG 7-day rain) vs normal.",
        "parameters": {"type": "object", "properties": {"rayon": {"type": "string", "description": "District name"}},
                       "required": ["rayon"]}}},
    {"type": "function", "function": {
        "name": "crop_recommendations", "description": "Ranked crop recommendations for a district (climate+soil "
        "suitability, historical yields, 2041-2050 projection).",
        "parameters": {"type": "object", "properties": {
            "rayon": {"type": "string"}, "irrigated": {"type": "boolean", "description": "Irrigated land"}},
            "required": ["rayon"]}}},
    {"type": "function", "function": {
        "name": "yield_history", "description": "Yearly yield of a crop in a district, national average and forecast.",
        "parameters": {"type": "object", "properties": {"rayon": {"type": "string"}, "crop": {"type": "string"}},
                       "required": ["rayon", "crop"]}}},
    {"type": "function", "function": {
        "name": "weather_forecast", "description": "Live 16-day weather forecast for a district.",
        "parameters": {"type": "object", "properties": {"rayon": {"type": "string"}}, "required": ["rayon"]}}},
    {"type": "function", "function": {
        "name": "country_overview", "description": "Country profile outside or including Azerbaijan: climate change "
        "(1981-90 vs 2016-25), 2041-50 projection, top crops and FAOSTAT yields.",
        "parameters": {"type": "object", "properties": {"country": {"type": "string", "description": "Country name or ISO3"}},
                       "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "world_crop_ranking", "description": "Countries ranked by FAOSTAT yield for a crop (world).",
        "parameters": {"type": "object", "properties": {"crop": {"type": "string"}, "year": {"type": "integer"}},
                       "required": ["crop"]}}},
    {"type": "function", "function": {
        "name": "crop_ranking", "description": "Districts ranked by yield for a crop.",
        "parameters": {"type": "object", "properties": {"crop": {"type": "string"},
                                                        "year": {"type": "integer"}}, "required": ["crop"]}}},
]


async def _run_tool(name, args):
    con = connect()
    try:
        r = services.find_rayon(con, args.get("rayon", "")) if "rayon" in args else None
        c = services.find_crop(con, args.get("crop", "")) if "crop" in args else None
    finally:
        con.close()
    if "rayon" in args and not r:
        return {"error": f"District '{args['rayon']}' not found"}
    if "crop" in args and not c:
        return {"error": f"Crop '{args['crop']}' not found"}
    if name == "rayon_profile":
        p = services.rayon_profile(r["id"])
        if p and p.get("fires"):
            p["fires"] = {k: v for k, v in p["fires"].items() if k != "points"}   # counts are enough for the model
        return p
    if name == "crop_recommendations":
        return services.recommendations(r["id"], args.get("irrigated", True), limit=10)
    if name == "yield_history":
        y = services.yield_series(r["id"], c["id"])
        y["series"] = y["series"][-12:]
        return {"rayon": r["name"], "crop": c["name"], **y}
    if name == "weather_forecast":
        f = await forecast(r["lat"], r["lon"])
        d = f["daily"]
        return {"rayon": r["name"], "days": [
            {"date": t, "tmin": d["temperature_2m_min"][i], "tmax": d["temperature_2m_max"][i],
             "precip_mm": d["precipitation_sum"][i], "gust_kmh": d["wind_gusts_10m_max"][i],
             "sky": WMO.get(d["weather_code"][i], "")} for i, t in enumerate(d["time"])]}
    if name == "country_overview":
        con = connect()
        try:
            q = args.get("country", "").strip()
            c = row(con, "SELECT iso3 FROM countries WHERE iso3=? OR lower(name)=lower(?) OR lower(name) LIKE lower(?)",
                    q.upper(), q, f"%{q}%")
        finally:
            con.close()
        if not c:
            return {"error": f"Country '{q}' not found"}
        p = services.country_profile(c["iso3"])
        p["units"] = [u["name"] for u in p["units"]][:60]
        return p
    if name == "world_crop_ranking":
        rk = services.world_ranking(c["id"], args.get("year"))
        rk["rows"] = [{k: x[k] for k in ("rank", "name", "yield", "production", "category")} for x in rk["rows"][:40]]
        return {"crop": c["name"], **rk}
    if name == "crop_ranking":
        rk = services.ranking(c["id"], args.get("year"))
        rk["rows"] = [{k: x[k] for k in ("rank", "name", "yield", "production", "category")} for x in rk["rows"]]
        return {"crop": c["name"], **rk}
    return {"error": "unknown tool"}


def enabled() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


STEP = {
    "rayon_profile": ("Reading district profile", "NASA POWER · SoilGrids · MODIS · SMAP · IMERG · FIRMS"),
    "crop_recommendations": ("Scoring crops for the district", "FAO ECOCROP · NEX-GDDP-CMIP6 · AzStat"),
    "yield_history": ("Loading yield history", "AzStat 2000–2025"),
    "weather_forecast": ("Fetching 16-day forecast", "Open-Meteo · ECMWF / ICON / GFS"),
    "crop_ranking": ("Ranking districts", "AzStat"),
    "country_overview": ("Reading country profile", "NASA POWER · NEX-GDDP-CMIP6 · FAOSTAT"),
    "world_crop_ranking": ("Ranking countries", "FAOSTAT"),
}


def _context(user, rayon_id):
    con = connect()
    try:
        hist = rows(con, "SELECT role, content FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT 12",
                    user["id"])[::-1]
        farms = rows(con, "SELECT f.name, r.name rayon FROM farms f JOIN rayons r ON r.id=f.rayon_id "
                          "WHERE f.user_id=?", user["id"])
    finally:
        con.close()
    ctx = ""
    if farms:
        ctx += "\nThe user's farms: " + "; ".join(f"{f['name']} ({f['rayon']})" for f in farms) + "."
    if rayon_id:
        ctx += f"\nThe user is currently viewing the '{rayon_id}' district page."
    msgs = [{"role": "system", "content": SYSTEM.format(today=date.today().isoformat(), ctx=ctx)}]
    msgs += [{"role": h["role"], "content": h["content"]} for h in hist]
    return msgs


async def answer_stream(user, message: str, rayon_id: str | None = None):
    """Yields events: step (tool started, with human label + data source), step_done, token (answer text as
    DeepSeek streams it), done. Every step shown in the UI is a real tool call against the database."""
    msgs = _context(user, rayon_id) + [{"role": "user", "content": message}]
    used, text = [], ""
    headers = {"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, read=120)) as client:
        for _ in range(6):
            content, calls = "", {}
            async with client.stream("POST", API_URL, headers=headers, json={
                    "model": MODEL, "messages": msgs, "tools": TOOLS, "temperature": 0.3, "stream": True}) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    delta = json.loads(data)["choices"][0].get("delta", {})
                    if delta.get("tool_calls") and not calls and content:
                        yield {"t": "reset"}       # text before a tool call was a preamble, not the answer
                    for tc in delta.get("tool_calls") or []:
                        c = calls.setdefault(tc["index"], {"id": "", "name": "", "args": ""})
                        c["id"] = tc.get("id") or c["id"]
                        fn = tc.get("function") or {}
                        c["name"] += fn.get("name") or ""
                        c["args"] += fn.get("arguments") or ""
                    piece = delta.get("content")
                    if piece:
                        content += piece
                        if not calls:          # final answer: forward tokens live
                            yield {"t": "token", "v": piece}
            if not calls:
                text = content
                break
            tool_calls = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["args"]}}
                          for _, c in sorted(calls.items())]
            msgs.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                label, src = STEP.get(name, (name, ""))
                detail = " · ".join(str(args[k]) for k in ("rayon", "crop", "year") if args.get(k))
                yield {"t": "step", "id": tc["id"], "label": label, "src": src, "detail": detail}
                try:
                    result = await _run_tool(name, args)
                    ok = not (isinstance(result, dict) and result.get("error"))
                except Exception as e:  # noqa: BLE001
                    result, ok = {"error": str(e)[:200]}, False
                used.append(name)
                yield {"t": "step_done", "id": tc["id"], "ok": ok}
                msgs.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:12000]})
        else:
            text = "Could not finish an answer, please simplify the question and try again."
            yield {"t": "token", "v": text}
    with tx() as con:
        con.execute("INSERT INTO chat_messages(user_id, role, content) VALUES(?,?,?)", (user["id"], "user", message))
        con.execute("INSERT INTO chat_messages(user_id, role, content) VALUES(?,?,?)", (user["id"], "assistant", text))
    yield {"t": "done", "tools": used}


async def answer(user, message: str, rayon_id: str | None = None) -> dict:
    text, tools = "", []
    async for ev in answer_stream(user, message, rayon_id):
        if ev["t"] == "token":
            text += ev["v"]
        elif ev["t"] == "reset":
            text = ""
        elif ev["t"] == "done":
            tools = ev["tools"]
    return {"answer": text, "tools": tools}
