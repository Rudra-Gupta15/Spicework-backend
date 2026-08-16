from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.core.config import USER_INFO_DIR
from backend.core.config import logger
from backend.models.audit import AuditData, HardwareDetails
from backend.services.common import clean_string, model_to_dict


def draw_page_decorations(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#A80000"))
    canvas.setLineWidth(1.5)
    canvas.rect(36, 36, doc.pagesize[0] - 72, doc.pagesize[1] - 72)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.HexColor("#A80000"))
    canvas.drawCentredString(doc.pagesize[0] / 2.0, 20, "INSPECTION REPORT BY INFRAPULSE IT MANAGEMENT")
    canvas.restoreState()


def pdf_text(value, style):
    return Paragraph(escape(clean_string(str(value), "-")), style)


def list_text(values):
    if not values:
        return "-"
    return ", ".join(clean_string(item, "") for item in values if clean_string(item, ""))


def apply_grid_style(table, header=False):
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style.extend([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F1F1")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    table.setStyle(TableStyle(style))
    return table


def add_pair_table(elements, title, rows, styles):
    table_rows = [[pdf_text(label, styles["bold"]), pdf_text(value, styles["normal"])] for label, value in rows]
    table = apply_grid_style(Table(table_rows, colWidths=[180, 324]))
    elements.append(KeepTogether([
        Paragraph(title, styles["section"]),
        table,
        Spacer(1, 12)
    ]))


def make_styles():
    return {
        "title":   ParagraphStyle("TitleStyle",   fontName="Helvetica-Bold", fontSize=15, leading=17, alignment=1, spaceAfter=18),
        "section": ParagraphStyle("SectionStyle", fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#A80000")),
        "bold":    ParagraphStyle("CellBold",      fontName="Helvetica-Bold", fontSize=9, leading=11),
        "normal":  ParagraphStyle("CellNormal",    fontName="Helvetica",      fontSize=9, leading=11),
        "small":   ParagraphStyle("CellSmall",     fontName="Helvetica",      fontSize=8, leading=10),
    }


def get_hw(data, key, fallback="Unknown"):
    hw = data.hardware_details
    if isinstance(hw, HardwareDetails):
        return getattr(hw, key, fallback)
    elif isinstance(hw, dict):
        return str(hw.get(key, fallback))
    return fallback


def get_hw_list(data, key):
    hw = data.hardware_details
    if isinstance(hw, HardwareDetails):
        return getattr(hw, key, [])
    elif isinstance(hw, dict):
        return hw.get(key, [])
    return []


def generate_pdf_for_device(client_id: str) -> str:
    """Dynamically build a ReportLab PDF report from the relational legacy_audits tables."""
    from backend import legacy_db

    audit = None
    try:
        audit = legacy_db.get_latest_audit(client_id)
    except Exception as e:
        logger.error(f"Error querying database for device '{client_id}': {e}")

    if not audit:
        return None

    try:
        hw_details = {
            "cpu": audit.get("cpu"), "ram": audit.get("ram"), "disk": audit.get("disk"),
            "serial_number": audit.get("serial_number"), "manufacturer": audit.get("manufacturer"),
            "model": audit.get("model"), "mobo_manufacturer": audit.get("mobo_manufacturer"),
            "mobo_product": audit.get("mobo_product"), "bios_version": audit.get("bios_version"),
            "bios_date": audit.get("bios_date"),
            "gpu_details": audit.get("gpus", []),
            "network_adapters": audit.get("network_adapters", []),
            "disk_partitions": audit.get("disk_partitions", []),
            "peripherals": audit.get("peripherals", []),
        }
        data = AuditData(
            computer_name=audit.get("computer_name") or client_id,
            current_user=audit.get("current_username") or "Unknown",
            os_name=audit.get("os_name") or "Windows / macOS",
            os_version=audit.get("os_version") or "",
            architecture=audit.get("architecture") or "64-bit",
            license_status=audit.get("license_status") or "Licensed",
            mac_address=audit.get("mac_address") or client_id,
            software_inventory=[
                {"name": s.get("application_name"), "version": s.get("version"),
                 "publisher": s.get("publisher"), "install_date": s.get("install_date")}
                for s in audit.get("software", [])
            ],
            hardware_details=hw_details,
            hotfixes=audit.get("hotfixes", []),
            printers=audit.get("printers", []),
            antivirus=audit.get("antivirus", []),
            user_accounts=[
                {"name": u.get("username"), "disabled": u.get("disabled"), "user_type": u.get("user_type")}
                for u in audit.get("user_accounts", [])
            ],
            login_history=audit.get("raw_login_history") or [],
            execution_datetime=audit.get("execution_datetime") or datetime.now().strftime("%d-%b-%Y_%H:%M:%S"),
        )

        clean_cid = "".join(x for x in client_id if x.isalnum() or x in "._-").strip() or "device"
        pdf_path = f"{USER_INFO_DIR}/AuditReport_{clean_cid}.pdf"

        doc = SimpleDocTemplate(
            pdf_path, pagesize=letter,
            leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
        )
        styles = make_styles()
        elements = [Paragraph("Compliance Inspection Report", styles["title"])]

        hw = data.hardware_details
        hw_d = hw if isinstance(hw, dict) else (model_to_dict(hw) if hw else {})

        # ── 1. Device & Scan Metadata ─────────────────────────────────────────
        add_pair_table(elements, "1. Device & Scan Metadata", [
            ("Computer Name",       data.computer_name),
            ("Execution DateTime",  data.execution_datetime),
            ("MAC Address",         data.mac_address),
            ("License Status",      data.license_status),
            ("Architecture",        data.architecture),
        ], styles)

        # ── 2. Operating System ───────────────────────────────────────────────
        add_pair_table(elements, "2. Operating System", [
            ("OS Name",             data.os_name),
            ("OS Version",          data.os_version),
            ("OS Architecture",     data.architecture),
        ], styles)

        # ── 3. Device Data ────────────────────────────────────────────────────
        add_pair_table(elements, "3. Device Data", [
            ("Hostname",            data.computer_name),
            ("Device Type",         hw_d.get("device_type", "—")),
            ("Manufacturer",        hw_d.get("manufacturer", "—")),
            ("Model",               hw_d.get("model", "—")),
            ("Serial Number",       hw_d.get("serial_number", "—")),
            ("Asset Tag",           hw_d.get("asset_tag", "—")),
            ("Domain",              hw_d.get("domain", "—")),
            ("Domain Role",         hw_d.get("domain_role", "—")),
            ("Description",         hw_d.get("description", "—")),
            ("Processor Name",      hw_d.get("processor_name", "—")),
            ("CPU Cores",           hw_d.get("cpu_cores", "—")),
            ("CPU Threads",         hw_d.get("cpu_threads", "—")),
            ("Installed RAM",       hw_d.get("installed_ram", "—")),
            ("RAM Slots",           hw_d.get("ram_slots", "—")),
            ("BIOS Version",        hw_d.get("bios_version", "—")),
            ("BIOS Date",           hw_d.get("bios_date", "—")),
            ("Last Backup",         hw_d.get("last_backup", "—")),
            ("Location",            hw_d.get("location_info", "—")),
        ], styles)

        # ── 4. Motherboard ────────────────────────────────────────────────────
        add_pair_table(elements, "4. Motherboard", [
            ("Manufacturer",        hw_d.get("mobo_manufacturer", "—")),
            ("Product",             hw_d.get("mobo_product", "—")),
            ("Version",             hw_d.get("mobo_version", "—")),
            ("Serial Number",       hw_d.get("mobo_serial", "—")),
        ], styles)

        # ── 5. Disk Information ───────────────────────────────────────────────
        disk_info_list = hw_d.get("disk_info", []) or hw_d.get("disks", [])
        if disk_info_list:
            disk_rows = [[
                pdf_text("Name", styles["bold"]), pdf_text("Model", styles["bold"]),
                pdf_text("Size", styles["bold"]), pdf_text("Free Space", styles["bold"]),
                pdf_text("SSD", styles["bold"]), pdf_text("Serial", styles["bold"]),
            ]]
            for di in disk_info_list:
                d = di if isinstance(di, dict) else model_to_dict(di)
                disk_rows.append([
                    pdf_text(str(d.get("name", "—")), styles["normal"]),
                    pdf_text(str(d.get("model", "—")), styles["normal"]),
                    pdf_text(str(d.get("size", "—")), styles["normal"]),
                    pdf_text(str(d.get("free_space", "—")), styles["normal"]),
                    pdf_text("Yes" if d.get("is_ssd") else "No", styles["normal"]),
                    pdf_text(str(d.get("serial_number", "—")), styles["normal"]),
                ])
            elements.append(KeepTogether([
                Paragraph("5. Disk Information", styles["section"]),
                apply_grid_style(Table(disk_rows, colWidths=[80, 130, 70, 80, 40, 104], repeatRows=1), header=True),
                Spacer(1, 12)
            ]))
        else:
            add_pair_table(elements, "5. Disk Information", [
                ("Logical Disk", hw_d.get("disk", "—")),
            ], styles)

        # ── 6. Partitions/Storage ─────────────────────────────────────────────
        dp_list = get_hw_list(data, "disk_partitions")
        dp_rows = [[
            pdf_text("Partition", styles["bold"]), pdf_text("File System", styles["bold"]),
            pdf_text("Size (GB)", styles["bold"]), pdf_text("Free (GB)", styles["bold"]),
            pdf_text("Bootable", styles["bold"]),
        ]]
        if dp_list:
            for p in dp_list:
                d = p if isinstance(p, dict) else model_to_dict(p)
                dp_rows.append([
                    pdf_text(str(d.get("name", "—")), styles["normal"]),
                    pdf_text(str(d.get("file_system_type", d.get("type", "—"))), styles["normal"]),
                    pdf_text(str(d.get("size_gb", "—")), styles["normal"]),
                    pdf_text(str(d.get("free_gb", "—")), styles["normal"]),
                    pdf_text(str(d.get("bootable", "—")), styles["normal"]),
                ])
        else:
            dp_rows.append([pdf_text("No partition data collected", styles["normal"])] + [pdf_text("—", styles["normal"])] * 4)
        elements.append(KeepTogether([
            Paragraph("6. Partitions / Storage", styles["section"]),
            apply_grid_style(Table(dp_rows, colWidths=[90, 100, 90, 90, 134], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── 7. Network Adapters ───────────────────────────────────────────────
        na_list = get_hw_list(data, "network_adapters")
        na_rows = [[
            pdf_text("Name", styles["bold"]), pdf_text("IPv4", styles["bold"]),
            pdf_text("Gateway", styles["bold"]), pdf_text("MAC", styles["bold"]),
            pdf_text("DNS Servers", styles["bold"]),
        ]]
        if na_list:
            for a in na_list:
                d = a if isinstance(a, dict) else model_to_dict(a)
                ipv4 = d.get("ipv4_addresses") or d.get("ip_address", "—")
                if isinstance(ipv4, list): ipv4 = ", ".join(ipv4)
                dns = d.get("dns_servers", "—")
                if isinstance(dns, list): dns = ", ".join(dns)
                na_rows.append([
                    pdf_text(str(d.get("name", "—")), styles["normal"]),
                    pdf_text(str(ipv4), styles["normal"]),
                    pdf_text(str(d.get("gateway", "—")), styles["normal"]),
                    pdf_text(str(d.get("mac_address", d.get("mac", "—"))), styles["normal"]),
                    pdf_text(str(dns), styles["normal"]),
                ])
        else:
            na_rows.append([pdf_text("No network adapter data collected", styles["normal"])] + [pdf_text("—", styles["normal"])] * 4)
        elements.append(KeepTogether([
            Paragraph("7. Network Adapters", styles["section"]),
            apply_grid_style(Table(na_rows, colWidths=[100, 90, 90, 100, 124], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── 8. Video Controllers / GPU ────────────────────────────────────────
        gpu_list = get_hw_list(data, "gpu_details")
        gpu_rows = [[
            pdf_text("GPU Name", styles["bold"]), pdf_text("Video Processor", styles["bold"]),
            pdf_text("Driver Version", styles["bold"]), pdf_text("VRAM", styles["bold"]),
        ]]
        if gpu_list:
            for g in gpu_list:
                d = g if isinstance(g, dict) else model_to_dict(g)
                gpu_rows.append([
                    pdf_text(str(d.get("name", "—")), styles["normal"]),
                    pdf_text(str(d.get("video_processor", d.get("processor", "—"))), styles["normal"]),
                    pdf_text(str(d.get("driver_version", "—")), styles["normal"]),
                    pdf_text(str(d.get("vram", "—")), styles["normal"]),
                ])
        else:
            gpu_rows.append([pdf_text("No GPU data collected", styles["normal"])] + [pdf_text("—", styles["normal"])] * 3)
        elements.append(KeepTogether([
            Paragraph("8. Video Controllers / Graphic", styles["section"]),
            apply_grid_style(Table(gpu_rows, colWidths=[160, 120, 110, 114], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── 9. Peripherals ────────────────────────────────────────────────────
        peri_list = get_hw_list(data, "peripherals")
        peri_rows = [[
            pdf_text("Name", styles["bold"]), pdf_text("Type", styles["bold"]),
            pdf_text("Manufacturer", styles["bold"]), pdf_text("Version", styles["bold"]),
        ]]
        if peri_list:
            for p in peri_list:
                d = p if isinstance(p, dict) else model_to_dict(p)
                peri_rows.append([
                    pdf_text(str(d.get("name", "—")), styles["normal"]),
                    pdf_text(str(d.get("type", "—")), styles["normal"]),
                    pdf_text(str(d.get("manufacturer", "—")), styles["normal"]),
                    pdf_text(str(d.get("version", "—")), styles["normal"]),
                ])
        else:
            peri_rows.append([pdf_text("No peripheral data collected", styles["normal"])] + [pdf_text("—", styles["normal"])] * 3)
        elements.append(KeepTogether([
            Paragraph("9. Peripherals", styles["section"]),
            apply_grid_style(Table(peri_rows, colWidths=[180, 110, 130, 84], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── 10. Users ─────────────────────────────────────────────────────────
        users_list = data.users if hasattr(data, "users") and data.users else []
        if not users_list:
            users_list = hw_d.get("users_list", [])
        user_rows = [[
            pdf_text("Username", styles["bold"]), pdf_text("Type", styles["bold"]),
            pdf_text("Domain", styles["bold"]), pdf_text("Status", styles["bold"]),
        ]]
        if users_list:
            for u in users_list:
                d = u if isinstance(u, dict) else model_to_dict(u)
                user_rows.append([
                    pdf_text(str(d.get("name", d.get("username", "—"))), styles["normal"]),
                    pdf_text(str(d.get("type", d.get("account_type", "—"))), styles["normal"]),
                    pdf_text(str(d.get("domain", "—")), styles["normal"]),
                    pdf_text(str(d.get("status", d.get("disabled", "—"))), styles["normal"]),
                ])
        else:
            user_rows.append([pdf_text("No user data collected", styles["normal"])] + [pdf_text("—", styles["normal"])] * 3)
        elements.append(KeepTogether([
            Paragraph("10. Users", styles["section"]),
            apply_grid_style(Table(user_rows, colWidths=[160, 110, 130, 104], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── 11. Recent Login History ──────────────────────────────────────────
        login_list = data.login_history if hasattr(data, "login_history") and data.login_history else []
        login_rows = [[
            pdf_text("Username", styles["bold"]), pdf_text("Domain", styles["bold"]),
            pdf_text("Logon Type", styles["bold"]), pdf_text("Time", styles["bold"]),
        ]]
        if login_list:
            for l in login_list[:50]:
                d = l if isinstance(l, dict) else model_to_dict(l)
                login_rows.append([
                    pdf_text(str(d.get("username", "—")), styles["normal"]),
                    pdf_text(str(d.get("domain", "—")), styles["normal"]),
                    pdf_text(str(d.get("logon_type", "—")), styles["normal"]),
                    pdf_text(str(d.get("time", d.get("timestamp", "—"))), styles["normal"]),
                ])
        else:
            login_rows.append([pdf_text("No login history collected", styles["normal"])] + [pdf_text("—", styles["normal"])] * 3)
        elements.append(KeepTogether([
            Paragraph("11. Recent Login History", styles["section"]),
            apply_grid_style(Table(login_rows, colWidths=[150, 110, 120, 124], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── 12. Installed Software Inventory ──────────────────────────────────
        sw_list = data.software_inventory or []
        sw_rows = [[
            pdf_text("App Name", styles["bold"]), pdf_text("Version", styles["bold"]),
            pdf_text("Publisher", styles["bold"]), pdf_text("Install Date", styles["bold"]),
        ]]
        for sw in sw_list[:200]:
            d = sw if isinstance(sw, dict) else model_to_dict(sw)
            sw_rows.append([
                pdf_text(str(d.get("name", "—")), styles["normal"]),
                pdf_text(str(d.get("version", "—")), styles["normal"]),
                pdf_text(str(d.get("publisher", "—")), styles["normal"]),
                pdf_text(str(d.get("install_date", "—")), styles["normal"]),
            ])
        elements.append(KeepTogether([
            Paragraph(f"12. Installed Software Inventory ({len(sw_list)} Total Apps)", styles["section"]),
            apply_grid_style(Table(sw_rows, colWidths=[200, 90, 150, 64], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        doc.build(elements, onFirstPage=draw_page_decorations, onLaterPages=draw_page_decorations)
        return pdf_path

    except Exception as err:
        logger.error(f"Failed to dynamically build PDF for {client_id}: {err}")
        return None
