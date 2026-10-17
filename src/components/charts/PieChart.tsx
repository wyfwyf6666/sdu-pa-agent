import { Pie } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  ChartData,
} from 'chart.js'

// 注册Chart.js组件
ChartJS.register(ArcElement, Tooltip, Legend)

interface PieChartProps {
  data: ChartData<'pie'>
}

export default function PieChart({ data }: PieChartProps) {
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
      },
    },
  }

  return <Pie options={options} data={data} />
} 