import type { ResponseWidget } from '../../../types'

type TableWidgetViewProps = {
  widget: Extract<ResponseWidget, { type: 'table' }>
}

export function TableWidgetView({ widget }: TableWidgetViewProps) {
  return (
    <section className="widget">
      <h3>{widget.title}</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {widget.table.columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {widget.table.rows.map((row) => (
              <tr key={row.join('-')}>
                {row.map((cell) => (
                  <td key={cell}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
