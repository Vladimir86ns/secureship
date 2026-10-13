import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import {
  useCreateCustomer,
  useDeleteCustomer,
  useListCustomers,
  useUpdateCustomer,
} from '../api/generated/admin/admin'
import type { CustomerIn, CustomerOut } from '../api/generated/models'
import { AdminResults } from './AdminResults'
import { adminErrorMessage } from './errors'
import { Field, TEXT_MAX_LENGTH } from './Field'
import { invalidateAdminQueries } from './invalidate'
import { matchesText, normalizeQuery } from './search'
import { SearchBox } from './SearchBox'

const EMPTY: CustomerIn = { first_name: '', last_name: '', address: '', phone_number: '' }

export function CustomersPage({ onShowShipments }: { onShowShipments: (customerId: string) => void }) {
  const queryClient = useQueryClient()
  const customers = useListCustomers()
  const create = useCreateCustomer()
  const update = useUpdateCustomer()
  const remove = useDeleteCustomer()

  const [editing, setEditing] = useState<CustomerOut | 'new' | null>(null)
  const [form, setForm] = useState<CustomerIn>(EMPTY)
  const [formError, setFormError] = useState<string | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  function openForm(customer: CustomerOut | 'new') {
    setEditing(customer)
    setFormError(null)
    setForm(
      customer === 'new'
        ? EMPTY
        : {
            first_name: customer.first_name,
            last_name: customer.last_name,
            address: customer.address,
            phone_number: customer.phone_number,
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
    else if (editing) update.mutate({ customerId: editing.id, data: form }, callbacks)
  }

  function deleteCustomer(customer: CustomerOut) {
    if (!window.confirm(`Delete customer ${customer.first_name} ${customer.last_name}?`)) return
    setListError(null)
    remove.mutate(
      { customerId: customer.id },
      {
        onSuccess: () => invalidateAdminQueries(queryClient),
        onError: (error) => setListError(adminErrorMessage(error)),
      },
    )
  }

  const saving = create.isPending || update.isPending
  const set = (key: keyof CustomerIn) => (value: string) => setForm((f) => ({ ...f, [key]: value }))

  const query = normalizeQuery(search)
  const visible = customers.data?.filter(
    (c) =>
      !query ||
      matchesText(query, [c.first_name, c.last_name, `${c.first_name} ${c.last_name}`, c.address, c.phone_number]),
  )

  return (
    <section>
      <div className="admin-toolbar">
        <h3>Customers</h3>
        <button type="button" className="admin-primary" onClick={() => openForm('new')}>
          New customer
        </button>
        <SearchBox value={search} onChange={setSearch} placeholder="Search customers…" />
      </div>

      {editing && (
        <form className="admin-form" onSubmit={save}>
          <h3>{editing === 'new' ? 'New customer' : `Edit ${editing.first_name} ${editing.last_name}`}</h3>
          <Field label="First name" value={form.first_name} onChange={set('first_name')} maxLength={TEXT_MAX_LENGTH} required />
          <Field label="Last name" value={form.last_name} onChange={set('last_name')} maxLength={TEXT_MAX_LENGTH} required />
          <Field label="Address (one line)" value={form.address} onChange={set('address')} maxLength={TEXT_MAX_LENGTH} required />
          <Field
            label="Phone (E.164, e.g. +15550100123)"
            value={form.phone_number}
            onChange={set('phone_number')}
            pattern="\+[1-9][0-9]{6,14}"
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
        {customers.isPending && <p>Loading…</p>}
        {customers.isError && <p className="admin-error">{adminErrorMessage(customers.error)}</p>}
        {customers.data?.length === 0 && <p className="admin-empty">No customers yet.</p>}
        {customers.data && customers.data.length > 0 && visible?.length === 0 && (
          <p className="admin-empty">No matches for “{search.trim()}”</p>
        )}
        {visible && visible.length > 0 && (
          <div className="admin-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Address</th>
                  <th>Phone</th>
                  <th>Shipments</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {c.first_name} {c.last_name}
                    </td>
                    <td>{c.address}</td>
                    <td>{c.phone_number}</td>
                    <td>
                      <button type="button" onClick={() => onShowShipments(c.id)}>
                        {c.shipment_count}
                      </button>
                    </td>
                    <td className="admin-actions">
                      <button type="button" onClick={() => openForm(c)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="admin-danger"
                        onClick={() => deleteCustomer(c)}
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
