import os
import pandas as pd
from app import app, db, EquipmentType, Equipment

def safe_str(val):
    """Safely converts Excel cells to strings, ignoring empty NaN values."""
    if pd.isna(val): return ""
    return str(val).strip()

def import_sheet(excel_filename, sheet_name, type_name, name_col, serial_col=None):
    try:
        print(f"Loading sheet: {sheet_name} as type '{type_name}'...")
        df = pd.read_excel(excel_filename, sheet_name=sheet_name)
        
        # Drop rows where the primary name column is completely empty
        if name_col in df.columns: 
            df = df.dropna(subset=[name_col])
            
        # 1. Ensure the EquipmentType exists in the V7 database
        eq_type = EquipmentType.query.filter_by(name=type_name).first()
        if not eq_type:
            eq_type = EquipmentType(name=type_name)
            db.session.add(eq_type)
            db.session.commit()

        # 2. Add the items dynamically
        added_count = 0
        for index, row in df.iterrows():
            name_val = safe_str(row.get(name_col))
            if not name_val:
                continue # Skip empty header rows

            serial = safe_str(row.get(serial_col)) if serial_col else ""
            raw_status = str(row.get('Status', '')).lower()
            is_paused = True if 'maintenance' in raw_status or 'broken' in raw_status else False
            
            # --- THE V7 MAGIC: DYNAMIC CUSTOM ATTRIBUTES ---
            # We gather all other columns (Location, OS, Layout, etc.) and save them as JSON!
            custom_attrs = {}
            exclude_cols = [name_col, serial_col, 'Status']
            
            for col in df.columns:
                if col not in exclude_cols and not str(col).startswith('Unnamed'):
                    val = safe_str(row.get(col))
                    # Only add the attribute if the cell isn't empty or a dash
                    if val and val != "nan" and val != "-":
                        custom_attrs[str(col).strip()] = val
            
            item = Equipment(
                type_id=eq_type.id, 
                name=name_val, 
                serial_no=serial, 
                is_paused=is_paused,
                custom_attributes=custom_attrs # Saves all extra Excel data here!
            )
            db.session.add(item)
            added_count += 1
        
        db.session.commit()
        print(f" -> Successfully imported {added_count} items into {type_name}!\n")
    except Exception as e:
        print(f" -> Error loading {sheet_name}: {e}\n")

if __name__ == '__main__':
    with app.app_context():
        excel_file = "eeg_equipment_2025_RCSE (1).xlsx"
        if not os.path.exists(excel_file):
            print(f"ERROR: Could not find '{excel_file}' in this folder!")
            print("Make sure the exact filename matches the script.")
        else:
            print("Starting V7 Dynamic Data Import...\n")
            
            # Mapped exactly to the sheet names and columns in your uploaded files!
            import_sheet(excel_file, "Amplifiers (eego)", "Amplifier", "Name of amplifier", "Serial no.")
            import_sheet(excel_file, "Caps", "Cap", "Name of cap", "Serial no.")
            import_sheet(excel_file, "Adapters", "Adapter", "Type of adapter", "Serial no.")
            import_sheet(excel_file, "recording Laptops", "Laptop", "Type of Laptop", "Serial no.")
            import_sheet(excel_file, "PCs", "PC", "Type of PC", "Serial no.")
            import_sheet(excel_file, "Cables", "Cable", "Type of cable", "Serial no.")
            import_sheet(excel_file, "USB Sticks", "USB Stick", "Type of USB-Stick")
            import_sheet(excel_file, "External devices", "External Drive", "External Drive", "Specific/SerienNummer")
            import_sheet(excel_file, "Additional", "Misc. Equipment", "Name of thing", "Serial no.")
            
            print("========================================")
            print("Data import complete! You can now run app.py")