-- Registered device estate behind /inventory/device: the units an organization
-- owns and hands out (laptops, printers, projectors, desktops), and the trail
-- of who has held each one.
--
-- Distinct from hardware_devices/device_inventory_current, which are machines
-- an agent audited. A unit here exists because someone bought it and typed it
-- in — it may never run an agent at all.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS registered_devices (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id         uuid REFERENCES sites(id) ON DELETE SET NULL,
    category        varchar(32)  NOT NULL,
    name            varchar(255) NOT NULL,
    serial_number   varchar(128) NOT NULL,
    buy_date        date,
    created_at      timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT registered_devices_category_check
        CHECK (category IN ('Laptop', 'Printer', 'Projector', 'Desktop')),

    -- The serial is the unit's identity, but only within the organization that
    -- registered it: two tenants can legitimately hold the same manufacturer
    -- serial, and neither should be able to see or block the other's.
    CONSTRAINT registered_devices_serial_per_org
        UNIQUE (organization_id, serial_number)
);

CREATE INDEX IF NOT EXISTS registered_devices_org_category_idx
    ON registered_devices (organization_id, category);

CREATE TABLE IF NOT EXISTS device_assignments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id   uuid NOT NULL REFERENCES registered_devices(id) ON DELETE CASCADE,
    user_name   varchar(255) NOT NULL,
    assigned_on date NOT NULL,
    -- NULL means the holder still has it; that open row is what makes the unit
    -- read as "Assigned" in the table.
    returned_on date,
    note        text,
    created_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT device_assignments_dates_check
        CHECK (returned_on IS NULL OR returned_on >= assigned_on)
);

CREATE INDEX IF NOT EXISTS device_assignments_device_idx
    ON device_assignments (device_id, assigned_on DESC);

-- A unit can be out with at most one holder at a time. Enforced here rather
-- than in application code so a concurrent double-assign cannot slip through.
CREATE UNIQUE INDEX IF NOT EXISTS device_assignments_one_open_per_device
    ON device_assignments (device_id)
    WHERE returned_on IS NULL;
