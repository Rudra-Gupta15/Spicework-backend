import os
import xml.etree.ElementTree as ET
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend import legacy_db
from backend.core.config import USER_INFO_DIR, logger
from backend.core.state import sessions
from backend.models.audit import AuditData, GpuInfo, HardwareDetails, HotfixData, NetworkDetails, PrinterData, UserAccount
from backend.services.common import clean_string, model_to_dict
from backend.services.pdf_report import (
    add_pair_table,
    apply_grid_style,
    draw_page_decorations,
    generate_pdf_for_device,
    get_hw,
    get_hw_list,
    list_text,
    make_styles,
    pdf_text,
)

router = APIRouter()


@router.post("/upload-audit")
def upload_audit(data: AuditData, client_id: str = Query(None)):
    cid = client_id or "unknown"
    logger.info(f"Uploading audit for client: {cid}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = "".join(x for x in data.computer_name if x.isalnum() or x in "._- ").strip() or "Unknown"

    session_meta  = sessions.get(cid, {})
    branch_name   = session_meta.get("branch_name",   "RELIGARE BROKING LIMITED")
    branch_code   = session_meta.get("branch_code",   "8301231")
    officer_name  = session_meta.get("officer_name",  "SANDIP BALIRAM LOKHANDE")
    available_pcs = session_meta.get("available_pcs", "1")
    registered_pcs = session_meta.get("registered_pcs", "1")
    audit_time    = data.execution_datetime if data.execution_datetime != "Unknown" else datetime.now().strftime("%d-%b-%Y_%H:%M:%S")

    json_path = f"{USER_INFO_DIR}/audit_{cid}_{clean_name}_{timestamp}.json"
    pdf_path  = f"{USER_INFO_DIR}/audit_{cid}_{clean_name}_{timestamp}.pdf"
    xml_path  = f"{USER_INFO_DIR}/audit_{cid}_{clean_name}_{timestamp}.xml"

    # Record current server timestamp for real-time sorting
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data.execution_datetime = ts

    audit_row = legacy_db.save_audit(data, client_id=cid)
    audit_id = audit_row["id"]


    av_str          = list_text(data.antivirus)
    compression_str = list_text(data.compression_utilities)

    # ── PDF Generation ────────────────────────────────────────────────────────
    try:
        doc = SimpleDocTemplate(
            pdf_path, pagesize=letter,
            leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
        )
        styles   = make_styles()
        elements = [Paragraph("Inspection Report", styles["title"])]

        # ── Summary Table ────────────────────────────────────────────────────
        cd_val      = "Not Installed" if data.drive_name == "No CD Unit Found" else data.drive_name
        printer_val = "Not Installed" if not data.printers else f"{len(data.printers)} connected"
        os_val      = "Not Installed" if data.os_name == "Unknown" else data.os_name
        av_val      = "Not Installed" if not data.antivirus or "No antivirus" in av_str else av_str
        comp_val    = "Not Installed" if not data.compression_utilities or "No compression" in compression_str else compression_str

        if cd_val == "Not Installed":
            cd_val += " (Reason: Modern laptops/desktops do not include CD drives)"
        if printer_val == "Not Installed":
            printer_val += " (Reason: Branch uses central networked printing)"
        if av_val == "Not Installed":
            av_val += " (Reason: Managed by Central IT / Default Defender used)"
        if comp_val == "Not Installed":
            comp_val += " (Reason: Not required for daily TIN-FC operations)"

        add_pair_table(elements, "User Details", [
            ("User Branch Name",    branch_name),
            ("User Branch Code",    branch_code),
            ("User Officer Name",   officer_name),
            ("Execution DateTime",  audit_time),
        ], styles)

        summary_style = [
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F1F1")),
            ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#F1F1F1")),
            ("BACKGROUND", (0, 6), (-1, 6), colors.HexColor("#F1F1F1")),
            ("SPAN",       (0, 0), (1, 0)),
            ("SPAN",       (0, 3), (1, 3)),
            ("SPAN",       (0, 6), (1, 6)),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME",   (0, 3), (-1, 3), "Helvetica-Bold"),
            ("FONTNAME",   (0, 6), (-1, 6), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ]
        summary_rows = [
            [pdf_text("Number of PCs (Desktop/Laptop) installed for TIN-FC", styles["bold"]), ""],
            [pdf_text("Available",   styles["normal"]), pdf_text(available_pcs,  styles["normal"])],
            [pdf_text("Registered",  styles["normal"]), pdf_text(registered_pcs, styles["normal"])],
            [pdf_text("Whether following hardware/peripherals has NOT been installed on PCs used for TIN-FC operations", styles["bold"]), ""],
            [pdf_text("CD Drive", styles["normal"]), pdf_text(cd_val,      styles["normal"])],
            [pdf_text("Printer",  styles["normal"]), pdf_text(printer_val, styles["normal"])],
            [pdf_text("Details of licenced softwares NOT installed on PCs used for TIN-FC operations", styles["bold"]), ""],
            [pdf_text("Operating System",   styles["normal"]), pdf_text(os_val,   styles["normal"])],
            [pdf_text("Anti-Virus",         styles["normal"]), pdf_text(av_val,   styles["normal"])],
            [pdf_text("Compression Utility", styles["normal"]), pdf_text(comp_val, styles["normal"])],
        ]
        summary_table = Table(summary_rows, colWidths=[360, 144])
        summary_table.setStyle(TableStyle(summary_style))
        elements.append(KeepTogether([summary_table, Spacer(1, 18)]))

        # ── OS Section ────────────────────────────────────────────────────────
        add_pair_table(elements, "Operating System", [
            ("OS Name",        data.os_name),
            ("OS Version",     data.os_version),
            ("OS Architecture", data.architecture),
            ("CS Name",        data.computer_name),
            ("License Status", data.license_status),
        ], styles)

        # ── Hotfixes ──────────────────────────────────────────────────────────
        hf_rows = [[
            pdf_text("#", styles["bold"]), pdf_text("Caption",     styles["bold"]),
            pdf_text("CS Name", styles["bold"]), pdf_text("Description", styles["bold"]),
            pdf_text("Fix ID", styles["bold"]), pdf_text("Installed On", styles["bold"]),
        ]]
        if data.hotfixes:
            for idx, hf in enumerate(data.hotfixes, 1):
                if isinstance(hf, HotfixData):
                    hf_rows.append([
                        pdf_text(idx, styles["normal"]), pdf_text(hf.caption, styles["normal"]),
                        pdf_text(hf.cs_name, styles["normal"]), pdf_text(hf.description, styles["normal"]),
                        pdf_text(hf.fix_id, styles["normal"]), pdf_text(hf.installed_on, styles["normal"]),
                    ])
                else:
                    hf_rows.append([
                        pdf_text(idx, styles["normal"]), pdf_text("", styles["normal"]),
                        pdf_text(data.computer_name, styles["normal"]), pdf_text("", styles["normal"]),
                        pdf_text(hf, styles["normal"]), pdf_text("", styles["normal"]),
                    ])
        else:
            hf_rows.append([pdf_text("-", styles["normal"])] + [pdf_text("-", styles["normal"])] * 5)
        elements.append(KeepTogether([
            Paragraph("OS Update Details", styles["section"]),
            apply_grid_style(Table(hf_rows, colWidths=[30, 160, 80, 94, 70, 70], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── MAC, Drive, Compression, AV ───────────────────────────────────────
        add_pair_table(elements, "Mac Address",               [("Mac Address", data.mac_address)], styles)
        add_pair_table(elements, "Drive Details",             [("Drive Name",  data.drive_name)],  styles)
        add_pair_table(elements, "Compression Utilities",     [("Installed",   compression_str)],  styles)
        add_pair_table(elements, "Antivirus",                 [("Installed AV", av_str)],          styles)

        # ── Printers ──────────────────────────────────────────────────────────
        pr_rows = [[
            pdf_text("#", styles["bold"]), pdf_text("Name",           styles["bold"]),
            pdf_text("SystemName", styles["bold"]), pdf_text("EnableBIDI", styles["bold"]),
            pdf_text("ExtendedStatus", styles["bold"]), pdf_text("PortName", styles["bold"]),
        ]]
        if data.printers:
            for idx, p in enumerate(data.printers, 1):
                if isinstance(p, PrinterData):
                    pr_rows.append([
                        pdf_text(idx, styles["normal"]), pdf_text(p.name, styles["normal"]),
                        pdf_text(p.system_name, styles["normal"]), pdf_text(p.enable_bidi, styles["normal"]),
                        pdf_text(p.extended_printer_status, styles["normal"]), pdf_text(p.port_name, styles["normal"]),
                    ])
                else:
                    pr_rows.append([
                        pdf_text(idx, styles["normal"]), pdf_text(p, styles["normal"]),
                        pdf_text(data.computer_name, styles["normal"]),
                        pdf_text("", styles["normal"]), pdf_text("", styles["normal"]), pdf_text("", styles["normal"]),
                    ])
        else:
            pr_rows.append([pdf_text("-", styles["normal"]), pdf_text("No printers detected", styles["normal"])] + [pdf_text("-", styles["normal"])] * 4)
        elements.append(KeepTogether([
            Paragraph("Printer Details", styles["section"]),
            apply_grid_style(Table(pr_rows, colWidths=[30, 180, 80, 64, 80, 70], repeatRows=1), header=True),
            pdf_text(f"Total Printers Connected: {len(data.printers)}", styles["bold"]),
            Spacer(1, 12)
        ]))

        # ── Hardware — Basic ──────────────────────────────────────────────────
        hw = data.hardware_details
        if isinstance(hw, HardwareDetails):
            add_pair_table(elements, "Hardware Details — Basic", [
                ("CPU",          hw.cpu),
                ("RAM",          hw.ram),
                ("Logical Disk", hw.disk),
            ], styles)
        elif isinstance(hw, dict) and hw:
            add_pair_table(elements, "Hardware Details — Basic", [
                ("CPU",          str(hw.get("cpu",  "Unknown"))),
                ("RAM",          str(hw.get("ram",  "Unknown"))),
                ("Logical Disk", str(hw.get("disk", "Unknown"))),
            ], styles)

        # ── Device Identity ───────────────────────────────────────────────────
        add_pair_table(elements, "Device Identity", [
            ("Serial Number", get_hw(data, "serial_number")),
            ("Manufacturer",  get_hw(data, "manufacturer")),
            ("Model",         get_hw(data, "model")),
        ], styles)

        # ── GPU Details ───────────────────────────────────────────────────────
        gpu_list = get_hw_list(data, "gpu_details")
        gpu_rows = [[pdf_text("GPU Name", styles["bold"]), pdf_text("Driver Version", styles["bold"]), pdf_text("VRAM", styles["bold"])]]
        if gpu_list:
            for g in gpu_list:
                if isinstance(g, GpuInfo):
                    gpu_rows.append([pdf_text(g.name, styles["normal"]), pdf_text(g.driver_version, styles["normal"]), pdf_text(g.vram, styles["normal"])])
                elif isinstance(g, dict):
                    gpu_rows.append([pdf_text(g.get("name",""), styles["normal"]), pdf_text(g.get("driver_version",""), styles["normal"]), pdf_text(g.get("vram",""), styles["normal"])])
        else:
            gpu_rows.append([pdf_text("No GPU data collected", styles["normal"]), pdf_text("-", styles["normal"]), pdf_text("-", styles["normal"])])
        elements.append(KeepTogether([
            Paragraph("GPU Details", styles["section"]),
            apply_grid_style(Table(gpu_rows, colWidths=[250, 130, 124], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── Physical Network Adapters ─────────────────────────────────────────
        na_list = get_hw_list(data, "network_adapters")
        na_rows = [[
            pdf_text("Adapter Name", styles["bold"]), pdf_text("Type", styles["bold"]),
            pdf_text("Speed", styles["bold"]), pdf_text("MAC Address", styles["bold"]),
        ]]
        if na_list:
            for a in na_list:
                d = a if isinstance(a, dict) else model_to_dict(a)
                na_rows.append([
                    pdf_text(d.get("name",""),         styles["normal"]),
                    pdf_text(d.get("adapter_type",""), styles["normal"]),
                    pdf_text(d.get("speed",""),        styles["normal"]),
                    pdf_text(d.get("mac_address",""),  styles["normal"]),
                ])
        else:
            na_rows.append([pdf_text("No adapter data", styles["normal"])] + [pdf_text("-", styles["normal"])] * 3)
        elements.append(KeepTogether([
            Paragraph("Physical Network Adapters", styles["section"]),
            apply_grid_style(Table(na_rows, colWidths=[200, 130, 100, 74], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── Disk Partitions ───────────────────────────────────────────────────
        dp_list = get_hw_list(data, "disk_partitions")
        dp_rows = [[
            pdf_text("Partition", styles["bold"]), pdf_text("Type", styles["bold"]),
            pdf_text("Size", styles["bold"]), pdf_text("Bootable", styles["bold"]),
        ]]
        if dp_list:
            for p in dp_list:
                d = p if isinstance(p, dict) else model_to_dict(p)
                dp_rows.append([
                    pdf_text(d.get("name",""),     styles["normal"]),
                    pdf_text(d.get("type",""),     styles["normal"]),
                    pdf_text(d.get("size_gb",""),  styles["normal"]),
                    pdf_text(d.get("bootable",""), styles["normal"]),
                ])
        else:
            dp_rows.append([pdf_text("No partition data", styles["normal"])] + [pdf_text("-", styles["normal"])] * 3)
        elements.append(KeepTogether([
            Paragraph("Disk Partitions", styles["section"]),
            apply_grid_style(Table(dp_rows, colWidths=[200, 120, 110, 74], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── Peripherals ───────────────────────────────────────────────────────
        peri_list = get_hw_list(data, "peripherals")
        peri_rows = [[pdf_text("Device Name", styles["bold"]), pdf_text("Type", styles["bold"]), pdf_text("Status", styles["bold"])]]
        if peri_list:
            for p in peri_list:
                d = p if isinstance(p, dict) else model_to_dict(p)
                peri_rows.append([
                    pdf_text(d.get("name",""),   styles["normal"]),
                    pdf_text(d.get("type",""),   styles["normal"]),
                    pdf_text(d.get("status",""), styles["normal"]),
                ])
        else:
            peri_rows.append([pdf_text("No peripheral data", styles["normal"]), pdf_text("-", styles["normal"]), pdf_text("-", styles["normal"])])
        elements.append(KeepTogether([
            Paragraph("Connected Peripherals", styles["section"]),
            apply_grid_style(Table(peri_rows, colWidths=[300, 120, 84], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── Network Details ───────────────────────────────────────────────────
        net_rows = [[pdf_text("IP Address", styles["bold"]), pdf_text("Gateway", styles["bold"]), pdf_text("MAC", styles["bold"])]]
        if data.network_details:
            for net in data.network_details:
                if isinstance(net, NetworkDetails):
                    net_rows.append([pdf_text(net.ip_address, styles["normal"]), pdf_text(net.gateway, styles["normal"]), pdf_text(net.mac, styles["normal"])])
                elif isinstance(net, dict):
                    net_rows.append([pdf_text(net.get("ip_address",""), styles["normal"]), pdf_text(net.get("gateway",""), styles["normal"]), pdf_text(net.get("mac",""), styles["normal"])])
        else:
            net_rows.append([pdf_text("-", styles["normal"]), pdf_text("No active adapters", styles["normal"]), pdf_text("-", styles["normal"])])
        elements.append(KeepTogether([
            Paragraph("Network Configuration", styles["section"]),
            apply_grid_style(Table(net_rows, colWidths=[168, 168, 168], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── User Accounts ─────────────────────────────────────────────────────
        usr_rows = [[pdf_text("Username", styles["bold"]), pdf_text("Disabled", styles["bold"])]]
        if data.user_accounts:
            for u in data.user_accounts:
                if isinstance(u, UserAccount):
                    usr_rows.append([pdf_text(u.name, styles["normal"]), pdf_text(u.disabled, styles["normal"])])
                elif isinstance(u, dict):
                    usr_rows.append([pdf_text(u.get("name",""), styles["normal"]), pdf_text(u.get("disabled",""), styles["normal"])])
        else:
            usr_rows.append([pdf_text("-", styles["normal"]), pdf_text("No local users found", styles["normal"])])
        elements.append(KeepTogether([
            Paragraph("Local User Accounts", styles["section"]),
            apply_grid_style(Table(usr_rows, colWidths=[252, 252], repeatRows=1), header=True),
            Spacer(1, 12)
        ]))

        # ── Software Inventory ────────────────────────────────────────────────
        sw_rows = [[
            pdf_text("#", styles["bold"]), pdf_text("Application Name", styles["bold"]),
            pdf_text("Version", styles["bold"]), pdf_text("Publisher", styles["bold"]),
            pdf_text("Install Date", styles["bold"]), pdf_text("Size", styles["bold"]),
        ]]
        if data.software_inventory:
            for idx, sw in enumerate(data.software_inventory, 1):
                d = sw if isinstance(sw, dict) else model_to_dict(sw)
                sw_rows.append([
                    pdf_text(idx,                    styles["small"]),
                    pdf_text(d.get("name",""),       styles["small"]),
                    pdf_text(d.get("version",""),    styles["small"]),
                    pdf_text(d.get("publisher",""),  styles["small"]),
                    pdf_text(d.get("install_date",""), styles["small"]),
                    pdf_text(d.get("size_mb",""),    styles["small"]),
                ])
        else:
            sw_rows.append([pdf_text("-", styles["normal"]), pdf_text("No software data collected", styles["normal"])] + [pdf_text("-", styles["normal"])] * 4)
        elements.append(Paragraph("Installed Software Inventory", styles["section"]))
        elements.append(pdf_text(f"Total Applications: {len(data.software_inventory)}", styles["bold"]))
        elements.append(Spacer(1, 6))
        elements.append(apply_grid_style(Table(sw_rows, colWidths=[28, 180, 70, 110, 68, 48], repeatRows=1), header=True))
        elements.append(Spacer(1, 12))

        doc.build(elements, onFirstPage=draw_page_decorations, onLaterPages=draw_page_decorations)
        logger.info(f"PDF built: {pdf_path}")

    except Exception as e:
        logger.error(f"PDF generation failed: {e}")

    # ── XML Generation ────────────────────────────────────────────────────────
    try:
        root = ET.Element("ComplianceAudit", version="3.0.0")

        meta = ET.SubElement(root, "UserDetails")
        ET.SubElement(meta, "BranchName").text     = branch_name
        ET.SubElement(meta, "BranchCode").text     = branch_code
        ET.SubElement(meta, "OfficerName").text    = officer_name
        ET.SubElement(meta, "ExecutionDateTime").text = audit_time

        os_xml = ET.SubElement(root, "OperatingSystem")
        ET.SubElement(os_xml, "OSName").text        = data.os_name
        ET.SubElement(os_xml, "OSVersion").text     = data.os_version
        ET.SubElement(os_xml, "OSArchitecture").text = data.architecture
        ET.SubElement(os_xml, "CSName").text        = data.computer_name
        ET.SubElement(os_xml, "LicenseStatus").text = data.license_status

        updates_xml = ET.SubElement(root, "OSUpdateDetails")
        for hf in data.hotfixes:
            item = ET.SubElement(updates_xml, "Hotfix")
            if isinstance(hf, HotfixData):
                ET.SubElement(item, "Caption").text     = hf.caption
                ET.SubElement(item, "CSName").text      = hf.cs_name
                ET.SubElement(item, "Description").text = hf.description
                ET.SubElement(item, "FixID").text       = hf.fix_id
                ET.SubElement(item, "InstalledOn").text = hf.installed_on
            else:
                ET.SubElement(item, "FixID").text = clean_string(hf, "")

        ET.SubElement(root, "MacAddress").text          = data.mac_address
        ET.SubElement(root, "DriveName").text           = data.drive_name
        ET.SubElement(root, "CompressionUtilities").text = compression_str
        ET.SubElement(root, "Antivirus").text           = av_str

        printers_xml = ET.SubElement(root, "PrinterDetails")
        for p in data.printers:
            item = ET.SubElement(printers_xml, "Printer")
            if isinstance(p, PrinterData):
                ET.SubElement(item, "Name").text                  = p.name
                ET.SubElement(item, "SystemName").text            = p.system_name
                ET.SubElement(item, "EnableBIDI").text            = p.enable_bidi
                ET.SubElement(item, "ExtendedPrinterStatus").text = p.extended_printer_status
                ET.SubElement(item, "PortName").text              = p.port_name
            else:
                ET.SubElement(item, "Name").text = clean_string(p, "")
        ET.SubElement(printers_xml, "TotalPrinterConnected").text = str(len(data.printers))

        hw_xml = ET.SubElement(root, "HardwareDetails")
        ET.SubElement(hw_xml, "CPU").text          = get_hw(data, "cpu")
        ET.SubElement(hw_xml, "RAM").text          = get_hw(data, "ram")
        ET.SubElement(hw_xml, "Disk").text         = get_hw(data, "disk")
        ET.SubElement(hw_xml, "SerialNumber").text = get_hw(data, "serial_number")
        ET.SubElement(hw_xml, "Manufacturer").text = get_hw(data, "manufacturer")
        ET.SubElement(hw_xml, "Model").text        = get_hw(data, "model")

        gpus_xml = ET.SubElement(hw_xml, "GPUList")
        for g in get_hw_list(data, "gpu_details"):
            d = g if isinstance(g, dict) else model_to_dict(g)
            gi = ET.SubElement(gpus_xml, "GPU")
            ET.SubElement(gi, "Name").text          = d.get("name", "")
            ET.SubElement(gi, "DriverVersion").text = d.get("driver_version", "")
            ET.SubElement(gi, "VRAM").text          = d.get("vram", "")

        nas_xml = ET.SubElement(hw_xml, "NetworkAdapters")
        for a in get_hw_list(data, "network_adapters"):
            d = a if isinstance(a, dict) else model_to_dict(a)
            ai = ET.SubElement(nas_xml, "Adapter")
            ET.SubElement(ai, "Name").text        = d.get("name", "")
            ET.SubElement(ai, "Type").text        = d.get("adapter_type", "")
            ET.SubElement(ai, "Speed").text       = d.get("speed", "")
            ET.SubElement(ai, "MACAddress").text  = d.get("mac_address", "")

        dps_xml = ET.SubElement(hw_xml, "DiskPartitions")
        for p in get_hw_list(data, "disk_partitions"):
            d = p if isinstance(p, dict) else model_to_dict(p)
            pi = ET.SubElement(dps_xml, "Partition")
            ET.SubElement(pi, "Name").text     = d.get("name", "")
            ET.SubElement(pi, "Type").text     = d.get("type", "")
            ET.SubElement(pi, "SizeGB").text   = d.get("size_gb", "")
            ET.SubElement(pi, "Bootable").text = d.get("bootable", "")

        peri_xml = ET.SubElement(hw_xml, "Peripherals")
        for p in get_hw_list(data, "peripherals"):
            d = p if isinstance(p, dict) else model_to_dict(p)
            pe = ET.SubElement(peri_xml, "Device")
            ET.SubElement(pe, "Name").text   = d.get("name", "")
            ET.SubElement(pe, "Type").text   = d.get("type", "")
            ET.SubElement(pe, "Status").text = d.get("status", "")

        sw_xml = ET.SubElement(root, "SoftwareInventory")
        ET.SubElement(sw_xml, "TotalInstalled").text = str(len(data.software_inventory))
        for sw in data.software_inventory:
            d = sw if isinstance(sw, dict) else model_to_dict(sw)
            si = ET.SubElement(sw_xml, "Application")
            ET.SubElement(si, "Name").text        = d.get("name", "")
            ET.SubElement(si, "Version").text     = d.get("version", "")
            ET.SubElement(si, "Publisher").text   = d.get("publisher", "")
            ET.SubElement(si, "InstallDate").text = d.get("install_date", "")
            ET.SubElement(si, "SizeMB").text      = d.get("size_mb", "")

        tree = ET.ElementTree(root)
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        logger.info(f"XML built: {xml_path}")

    except Exception as e:
        logger.error(f"XML generation failed: {e}")

    if not os.path.exists(pdf_path) or not os.path.exists(xml_path):
        sessions[cid] = {
            "status": "failed", "branch_name": branch_name, "branch_code": branch_code,
            "officer_name": officer_name, "error": "Report generation failed.",
            "pdf_path": pdf_path if os.path.exists(pdf_path) else None,
            "xml_path": xml_path if os.path.exists(xml_path) else None,
        }
        raise HTTPException(status_code=500, detail="Audit report generation failed.")

    legacy_db.update_audit_report_paths(
        audit_id,
        pdf_path if os.path.exists(pdf_path) else None,
        xml_path if os.path.exists(xml_path) else None,
    )

    sessions[cid] = {
        "status": "completed", "branch_name": branch_name, "branch_code": branch_code,
        "officer_name": officer_name, "pdf_path": pdf_path, "xml_path": xml_path,
    }


@router.get("/download-report")
def download_report(client_id: str = Query(...), format: str = Query("pdf"), action: str = Query("download")):
    fp = None
    session = sessions.get(client_id)
    if session and session.get("pdf_path") and os.path.exists(session["pdf_path"]):
        fp = session["pdf_path"]
    else:
        fp = generate_pdf_for_device(client_id)

    if not fp or not os.path.exists(fp):
        raise HTTPException(status_code=404, detail=f"Audit report for device '{client_id}' not found.")

    disposition = "inline" if action == "view" else "attachment"
    clean_mac_name = client_id.replace(":", "_").replace(" ", "_")
    download_filename = f"AuditReport_{clean_mac_name}.pdf"
    return FileResponse(fp, media_type="application/pdf", filename=download_filename, content_disposition_type=disposition)


@router.get("/api/download-device-pdf/{device_id}")
def api_download_device_pdf(device_id: str, action: str = Query("download")):
    fp = generate_pdf_for_device(device_id)
    if not fp or not os.path.exists(fp):
        raise HTTPException(status_code=404, detail=f"No audit report found for device '{device_id}'.")
    clean = device_id.replace(":", "_").replace(" ", "_")
    disposition = "inline" if action == "view" else "attachment"
    return FileResponse(fp, media_type="application/pdf", filename=f"AuditReport_{clean}.pdf", content_disposition_type=disposition)
