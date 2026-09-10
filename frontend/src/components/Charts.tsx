import { lazy, Suspense } from 'react'
import { Spin } from 'antd'

// 懒加载 @ant-design/charts，避免图表库打进主 chunk（现有 chunk 已 1.37MB）
const Pie = lazy(() => import('@ant-design/charts').then((m) => ({ default: m.Pie })))
const Column = lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Column })),
)
const Line = lazy(() => import('@ant-design/charts').then((m) => ({ default: m.Line })))

const fallback = (
  <div style={{ textAlign: 'center', padding: 40 }}>
    <Spin />
  </div>
)

export interface ChartDatum {
  [key: string]: string | number
}

/** 饼图（风险档/账龄段分布） */
export function PieChart({
  data,
  angleField,
  colorField,
}: {
  data: ChartDatum[]
  angleField: string
  colorField: string
}) {
  return (
    <Suspense fallback={fallback}>
      <Pie
        data={data}
        angleField={angleField}
        colorField={colorField}
        label={{ text: angleField, position: 'inside' }}
        height={260}
      />
    </Suspense>
  )
}

/** 柱图（账龄分布/各档催收效果） */
export function ColumnChart({
  data,
  xField,
  yField,
  colorField,
}: {
  data: ChartDatum[]
  xField: string
  yField: string
  colorField?: string
}) {
  return (
    <Suspense fallback={fallback}>
      <Column
        data={data}
        xField={xField}
        yField={yField}
        colorField={colorField}
        height={260}
      />
    </Suspense>
  )
}

/** 折线图（周/月趋势） */
export function LineChart({
  data,
  xField,
  yField,
  colorField,
}: {
  data: ChartDatum[]
  xField: string
  yField: string
  colorField?: string
}) {
  return (
    <Suspense fallback={fallback}>
      <Line
        data={data}
        xField={xField}
        yField={yField}
        colorField={colorField}
        height={300}
        point={{ shapeField: 'circle', sizeField: 3 }}
      />
    </Suspense>
  )
}
