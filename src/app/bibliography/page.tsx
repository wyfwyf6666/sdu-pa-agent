"use client"

import React, { useEffect, useState, useCallback } from "react"
import { Card, Button, Select, Input, Table, Tag, message, Space, Typography, Statistic, Row, Col, Popconfirm } from "antd"
import { UploadOutlined, SearchOutlined, DeleteOutlined, DatabaseOutlined } from "@ant-design/icons"
import MainLayout from "@/components/layout/MainLayout"
import ContentLayout from "@/components/layout/ContentLayout"
import { isAuthenticated } from "@/lib/api"
import { useRouter } from "next/navigation"

const { Title, Text } = Typography
const API = "/api/v1"

export default function BibliographyPage() {
  const router = useRouter()
  const [file, setFile] = useState<File | null>(null)
  const [sourceName, setSourceName] = useState("CNKI")
  const [batches, setBatches] = useState<any[]>([])
  const [query, setQuery] = useState("")
  const [records, setRecords] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [totalRecords, setTotalRecords] = useState(0)

  useEffect(() => {
    if (typeof window !== "undefined" && !isAuthenticated()) { router.push("/login"); return }
    loadData()
  }, [])

  const api = useCallback(async (url: string, opts?: RequestInit) => {
    const t = localStorage.getItem("token")
    const r = await fetch(url, { ...opts, headers: { ...opts?.headers, ...(t ? { Authorization: `Bearer ${t}` } : {}) } })
    if (r.status === 401) { localStorage.removeItem("token"); router.push("/login"); throw new Error("未登录") }
    return r
  }, [router])

  const safeJson = async (r: Response) => {
    const text = await r.text()
    let d: any = {}
    try { d = text ? JSON.parse(text) : {} } catch { d = { detail: text || "服务器错误" } }
    if (!r.ok) throw new Error(d.detail || `请求失败(${r.status})`)
    return d
  }

  async function loadData() {
    try { const d = await safeJson(await api(`${API}/bibliography/imports`)); setBatches(d.items || []); setTotalRecords(d.total_records || 0) } catch {}
    try { const d = await safeJson(await api(`${API}/bibliography/search`)); setRecords(d.items || []) } catch {}
  }

  async function doSearch() {
    try { const d = await safeJson(await api(`${API}/bibliography/search?q=${encodeURIComponent(query)}&limit=50`)); setRecords(d.items || []) } catch {}
  }

  async function doImport() {
    if (!file) { message.warning("请选择文件"); return }
    const fd = new FormData(); fd.append("file", file); fd.append("source_name", sourceName)
    setLoading(true)
    try {
      const r = await api(`${API}/bibliography/import`, { method: "POST", body: fd })
      const d = await safeJson(r)
      message.success(`成功导入 ${d.success_count} 条（重复 ${d.duplicate_count} 条）`)
      await loadData()
    } catch (e: any) { message.error(e.message) }
    finally { setLoading(false) }
  }

  async function delBatch(id: string) {
    try { await api(`${API}/bibliography/imports/${id}`, { method: "DELETE" }); message.success("已删除"); loadData() } catch {}
  }

  return (
    <MainLayout>
      <ContentLayout>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 16px" }}>
          <Title level={3}><DatabaseOutlined style={{ marginRight: 8, color: "#7A1014" }} />本地题录库</Title>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}><Card size="small"><Statistic title="题录总数" value={totalRecords} /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="导入批次" value={batches.length} /></Card></Col>
          </Row>

          <Card title="导入题录" style={{ marginBottom: 24 }}
            extra={<Space><Select value={sourceName} onChange={setSourceName} style={{ width: 180 }}>
              {["CNKI","万方","维普","Web of Science","Scopus","其他"].map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
            </Select></Space>}>
            <Space>
              <input type="file" accept=".txt,.csv,.xlsx,.json" onChange={e => setFile(e.target.files?.[0] || null)} />
              <Button type="primary" icon={<UploadOutlined />} onClick={doImport} loading={loading} style={{ background: "#7A1014" }}>导入</Button>
            </Space>
            <Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>支持 TXT（GB/T 7714）、CSV、Excel、JSON</Text>
          </Card>

          <Card title="导入批次" style={{ marginBottom: 24 }}>
            <Table dataSource={batches} rowKey="id" size="small" pagination={{ pageSize: 10 }}
              columns={[
                { title: "文件", dataIndex: "file_name", ellipsis: true }, { title: "格式", dataIndex: "file_type", width: 80 },
                { title: "来源", dataIndex: "source_name", width: 100 },
                { title: "成功", dataIndex: "success_count", width: 60 }, { title: "重复", dataIndex: "duplicate_count", width: 60 },
                { title: "状态", dataIndex: "status", width: 80, render: (s: string) => <Tag color={s === "success" ? "green" : "red"}>{s}</Tag> },
                { title: "操作", width: 80, render: (_: any, r: any) => <Popconfirm title="确定删除？" onConfirm={() => delBatch(r.id)}><Button size="small" danger icon={<DeleteOutlined />} /></Popconfirm> },
              ]} />
          </Card>

          <Card title="搜索题录">
            <Space style={{ marginBottom: 12 }}>
              <Input.Search value={query} onChange={e => setQuery(e.target.value)} onSearch={doSearch} placeholder="题名、作者、期刊、DOI" style={{ width: 360 }} enterButton={<><SearchOutlined /> 搜索</>} />
            </Space>
            <Table dataSource={records} rowKey="id" size="small" pagination={{ pageSize: 20 }}
              columns={[
                { title: "题名", dataIndex: "title", ellipsis: true, width: 250, render: (t: string) => <Text style={{ fontSize: 13 }}>{t}</Text> },
                { title: "作者", dataIndex: "authors", width: 120, ellipsis: true }, { title: "年份", dataIndex: "year", width: 60 },
                { title: "来源", dataIndex: "journal", width: 150, ellipsis: true, render: (t: string, r: any) => t || r.publisher || "-" },
                { title: "DOI", dataIndex: "doi", width: 120, ellipsis: true }, { title: "平台", dataIndex: "source_name", width: 80 },
              ]} />
          </Card>
        </div>
      </ContentLayout>
    </MainLayout>
  )
}
