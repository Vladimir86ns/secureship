import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import {
  useCreatePackage,
  useDeletePackage,
  useListPackages,
  useListShipments,
  useUpdatePackage,
} from '../api/generated/admin/admin'
import type { PackageIn, PackageOut } from '../api/generated/models'
import { AdminResults } from './AdminResults'
import { adminErrorMessage } from './errors'
import { DESCRIPTION_MAX_LENGTH, Field } from './Field'
import { invalidateAdminQueries } from './invalidate'
import { matchesText, matchesTracking, normalizeQuery } from './search'
import { SearchBox } from './SearchBox'

// Decimals are kept as strings end to end (the API accepts and returns them as strings), so nothing is rounded.
type PackageForm = Omit<PackageIn, 'weight_kg' | 'declared_value'> & { weight_kg: string; declared_value: string }

function emptyPackage(shipmentId: string | null): PackageForm {
  return { shipment_id: shipmentId ?? '', description: '', weight_kg: '', declared_value: '' }
}

type Props = {
  shipmentId: string | null
  onShipmentChange: (shipmentId: string | null) => void
}

export function PackagesPage({ shipmentId, onShipmentChange }: Props) {
  const queryClient = useQueryClient()
  const shipments = useListShipments()
  const packages = useListPackages(shipmentId ? { shipment_id: shipmentId } : undefined)
  const create = useCreatePackage()
  const update = useUpdatePackage()
  const remove = useDeletePackage()

  const [editing, setEditing] = useState<PackageOut | 'new' | null>(null)
  const [form, setForm] = useState<PackageForm>(emptyPackage(null))
  const [formError, setFormError] = useState<string | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  function openForm(pkg: PackageOut | 'new') {
    setEditing(pkg)
    setFormError(null)
    setForm(
      pkg === 'new'
        ? emptyPackage(shipmentId)
        : {
            shipment_id: pkg.shipment_id,
            description: pkg.description,
            weight_kg: pkg.weight_kg,
            declared_value: pkg.declared_value,
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
    const data: PackageIn = form
    if (editing === 'new') create.mutate({ data }, callbacks)
    else if (editing) update.mutate({ packageId: editing.id, data }, callbacks)
  }

  function deletePackage(pkg: PackageOut) {
    if (!window.confirm(`Delete package "${pkg.description}" of shipment ${pkg.tracking_number}?`)) return
    setListError(null)
    remove.mutate(
      { packageId: pkg.id },
      {
        onSuccess: () => invalidateAdminQueries(queryClient),
        onError: (error) => setListError(adminErrorMessage(error)),
      },
    )
  }

  const saving = create.isPending || update.isPending
  const set = (key: keyof PackageForm) => (value: string) => setForm((f) => ({ ...f, [key]: value }))

  const query = normalizeQuery(search)
  const visible = packages.data?.filter(
    (p) => !query || matchesTracking(query, p.tracking_number) || matchesText(query, [p.description]),
  )

  return (
    <section>
      <div className="admin-toolbar">
        <h3>Packages</h3>
        <label>
          Shipment
          <select value={shipmentId ?? ''} onChange={(e) => onShipmentChange(e.target.value || null)}>
            <option value="">All shipments</option>
            {shipments.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.tracking_number} ({s.customer_name})
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="admin-primary" onClick={() => openForm('new')}>
          New package
        </button>
        <SearchBox value={search} onChange={setSearch} placeholder="Search packages…" />
      </div>

      {editing && (
        <form className="admin-form" onSubmit={save}>
          <h3>{editing === 'new' ? 'New package' : `Edit "${editing.description}"`}</h3>
          <label>
            Shipment
            <select value={form.shipment_id} onChange={(e) => set('shipment_id')(e.target.value)} required>
              <option value="" disabled>
                Choose a shipment
              </option>
              {shipments.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.tracking_number} ({s.customer_name})
                </option>
              ))}
            </select>
            {shipments.data?.length === 0 && <span className="admin-hint">Create a shipment first.</span>}
          </label>
          <Field label="Description" value={form.description} onChange={set('description')} maxLength={DESCRIPTION_MAX_LENGTH} required />
          <Field
            label="Weight (kg)"
            type="number"
            min="0.001"
            step="0.001"
            value={form.weight_kg}
            onChange={set('weight_kg')}
            required
          />
          <Field
            label="Declared value"
            type="number"
            min="0"
            step="0.01"
            value={form.declared_value}
            onChange={set('declared_value')}
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
        {packages.isPending && <p>Loading…</p>}
        {packages.isError && <p className="admin-error">{adminErrorMessage(packages.error)}</p>}
        {packages.data?.length === 0 && (
          <p className="admin-empty">{shipmentId ? 'No packages for this shipment.' : 'No packages yet.'}</p>
        )}
        {packages.data && packages.data.length > 0 && visible?.length === 0 && (
          <p className="admin-empty">No matches for “{search.trim()}”</p>
        )}
        {visible && visible.length > 0 && (
          <div className="admin-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Shipment</th>
                  <th>Description</th>
                  <th>Weight (kg)</th>
                  <th>Declared value</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((p) => (
                  <tr key={p.id}>
                    <td>{p.tracking_number}</td>
                    <td>{p.description}</td>
                    <td>{p.weight_kg}</td>
                    <td>{p.declared_value}</td>
                    <td className="admin-actions">
                      <button type="button" onClick={() => openForm(p)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="admin-danger"
                        onClick={() => deletePackage(p)}
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
