import axios from 'axios';
import { API_BASE_URL } from '../config';

export interface HistoryItem {
  id: string;
  type: 'document'|'chat'|'login'|'upload'|'approval';
  title: string;
  description: string;
  timestamp: string;    // ISO 字符串
  status?: 'success'|'error'|'pending';
  user?: string;
  // details 根据后端返回而定
  details?: {
    fileSize?: string;
    duration?: string;
    result?: string;
  };
}

interface ListParams {
  start?: string;  // ISO
  end?: string;
  type?: string;
  query?: string;
}

export async function fetchHistory(params: ListParams = {}): Promise<HistoryItem[]> {
  const res = await axios.get<HistoryItem[]>(`${API_BASE_URL}/history`, { params });
  return res.data;
}
