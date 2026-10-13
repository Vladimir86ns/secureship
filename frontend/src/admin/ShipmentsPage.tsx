import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import {
  useCreateShipment,
  useDeleteShipment,
  useListCustomers,
  useListShipments,
  useUpdateShipment,
} from '../api/generated/admin/admin'
import { ShipmentStatus, type ShipmentIn, type ShipmentOut } from '../api/generated/models'
import { AdminResults } from './AdminResults'
import { adminErrorMessage } from './errors'
import { Field, TEXT_MAX_LENGTH } from './Field'
import { invalidateAdminQueries } from './invalidate'
import { matchesText, matchesTracking, normalizeQuery } from './search'
import { SearchBox } from './SearchBox'

const STATUSES = Object.values(ShipmentStatus)

function emptyShipment(customerId: string | null): ShipmentIn {
  return {
    customer_id: customerId ?? '',
    tracking_number: '',
    status: ShipmentStatus.label_created,
    carrier: '',
    origin: '',
    destination: '',
    estimated_delivery: '',
  }
}

type Props = {
  customerId: string | null
  onCustomerChange: (customerId: string | null) => void
  onShowPackages: (shipmentId: string) => void
}

export function ShipmentsPage({ customerId, onCustomerChange, onShowPackages }: Props) {
  const queryClient = useQueryClient()
  const customers = useListCustomers()
  const shipments = useListShipments(customerId ? { customer_id: customerId } : undefined)
  const create = useCreateShipment()
  const update = useUpdateShipment()
  const remove = useDeleteShipment()

  const [editing, setEditing] = useState<ShipmentOut | 'new' | null>(null)
  const [form, setForm] = useState<ShipmentIn>(emptyShipment(null))
  const [formError, setFormError] = useState<string | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  function openForm(shipment: ShipmentOut | 'new') {
    setEditing(shipment)
    setFormError(null)
    setForm(
      shipment === 'new'
        ? emptyShipment(customerId)
        : {
            customer_id: shipment.customer_id,
            tracking_number: shipment.tracking_number,
            status: shipment.status,
            carrier: shipment.carrier,
            origin: shipment.origin,
            destination: shipment.destination,
            estimated_delivery: shipment.estimated_delivery,
          },
    )
  }

  const callbacks = {
    onSuccess: async () => {
      setEditing(null)
      await invalidateAdminQueries(queryClient)
    },
    onError: (error: unknown) => setFormError(adminErrorMessage(error)),
  }

  function save(e: FormEvent) {
    e.preventDefault()
    if (editing === 'new') create.mutate({ data: form }, callbacks)
    else if (editing) update.mutate({ shipmentId: editing.id, data: form }, callbacks)
  }

  function deleteShipment(shipment: ShipmentOut) {
    const packages = shipment.package_count ? ` and its ${shipment.package_count} package(s)` : ''
    if (!window.confirm(`Delete shipment ${shipment.tracking_number}${packages}?`)) return
    setListError(null)
    remove.mutate(
      { shipmentId: shipment.id },
      {
        onSuccess: () => invalidateAdminQueries(queryClient),
        onError: (error) => setListError(adminErrorMessage(error)),
      },
    )
  }

  const saving = create.isPending || update.isPending
  const set = (key: keyof ShipmentIn) => (value: string) => setForm((f) => ({ ...f, [key]: value }))

  const query = normalizeQuery(search)
  const visible = shipments.data?.filter(
    (s) =>
      !query ||
      matchesTracking(query, s.tracking_number) ||
      matchesText(query, [s.customer_name, s.status, s.carrier, s.origin, s.destination]),
  )

  return (
    <section>
      <div className="admin-toolbar">
        <h3>Shipments</h3>
        <label>
          Customer
          <select value={customerId ?? ''} onChange={(e) => onCustomerChange(e.target.value || null)}>
            <option value="">All customers</option>
            {customers.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.first_name} {c.last_name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="admin-primary" onClick={() => openForm('new')}>
          New shipment
        </button>
        <SearchBox value={search} onChange={setSearch} placeholder="Search shipments…" />
      </div>

      {editing && (
        <form className="admin-form" onSubmit={save}>
          <h3>{editing === 'new' ? 'New shipment' : `Edit ${editing.tracking_number}`}</h3>
          <label>
            Customer
            <select value={form.customer_id} onChange={(e) => set('customer_id')(e.target.value)} required>
              <option value="" disabled>
                Choose a customer
              </option>
              {customers.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.first_name} {c.last_name}
                </option>
              ))}
            </select>
            {customers.data?.length === 0 && <span className="admin-hint">Create a customer first.</span>}
          </label>
          <Field label="Tracking number" value={form.tracking_number} onChange={set('tracking_number')} required />
          <label>
            Status
            <select value={form.status} onChange={(e) => set('status')(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <Field label="Carrier" value={form.carrier} onChange={set('carrier')} maxLength={TEXT_MAX_LENGTH} required />
          <Field label="Origin" value={form.origin} onChange={set('origin')} maxLength={TEXT_MAX_LENGTH} required />
          <Field label="Destination" value={form.destination} onChange={set('destination')} maxLength={TEXT_MAX_LENGTH} required />
          <Field
            label="Estimated delivery"
            type="date"
            value={form.estimated_delivery}
            onChange={set('estimated_delivery')}
            required
          />
          {formError && <p className="admin-error">{formError}</p>}
          <div className="admin-form-actions">
            <button type="submit" className="admin-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button type="button" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      <AdminResults query={query}>
        {listError && <p className="admin-error">{listError}</p>}
        {shipments.isPending && <p>Loading…</p>}
        {shipments.isError && <p className="admin-error">{adminErrorMessage(shipments.error)}</p>}
        {shipments.data?.length === 0 && (
          <p className="admin-empty">{customerId ? 'No shipments for this customer.' : 'No shipments yet.'}</p>
        )}
        {shipments.data && shipments.data.length > 0 && visible?.length === 0 && (
          <p className="admin-empty">No matches for “{search.trim()}”</p>
        )}
        {visible && visible.length > 0 && (
          <div className="admin-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tracking number</th>
                  <th>Customer</th>
                  <th>Status</th>
                  <th>Carrier</th>
                  <th>Route</th>
                  <th>Est. delivery</th>
                  <th>Last update</th>
                  <th>Packages</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((s) => (
                  <tr key={s.id}>
                    <td>{s.tracking_number}</td>
                    <td>{s.customer_name}</td>
                    <td>{s.status}</td>
                    <td>{s.carrier}</td>
                    <td>
                      {s.origin} → {s.destination}
                    </td>
                    <td>{s.estimated_delivery}</td>
                    <td>{new Date(s.last_update).toLocaleString()}</td>
                    <td>
                      <button type="button" onClick={() => onShowPackages(s.id)}>
                        {s.package_count}
                      </button>
                    </td>
                    <td className="admin-actions">
                      <button type="button" onClick={() => openForm(s)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="admin-danger"
                        onClick={() => deleteShipment(s)}
                        disabled={remove.isPending}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AdminResults>
    </section>
  )
}
