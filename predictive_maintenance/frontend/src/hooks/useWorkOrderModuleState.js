import { useEffect, useState } from 'react'

import WorkOrderApiService from '../services/workorderApi'
import { getInitialWorkOrders } from '../services/workorderMockAdapter'

export default function useWorkOrderModuleState() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [workOrders, setWorkOrders] = useState(getInitialWorkOrders)
  const [llmStatus, setLlmStatus] = useState({ checked: false, available: false, model: '' })

  useEffect(() => {
    let mounted = true
    WorkOrderApiService.getStatus().then(({ ok, data }) => {
      if (!mounted) return
      if (ok && data) {
        setLlmStatus({
          checked: true,
          available: data.llm_available,
          model: data.model || '',
          fallback: data.fallback_active,
        })
      } else {
        setLlmStatus({ checked: true, available: false, model: '', fallback: true })
      }
    })
    return () => {
      mounted = false
    }
  }, [])

  const addWorkOrder = (wo) => {
    setWorkOrders((prev) => [wo, ...prev])
  }

  return {
    activeTab,
    setActiveTab,
    workOrders,
    setWorkOrders,
    addWorkOrder,
    llmStatus,
  }
}
