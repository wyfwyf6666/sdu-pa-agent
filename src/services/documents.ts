import axios from 'axios';
import { API_BASE_URL } from '../config';

export interface Document {
  filename: string;
  size: number;
  upload_time: string;
}

export async function downloadDocument(filename: string) {
  const res = await fetch(
    `${API_BASE_URL}/documents/download?filename=${encodeURIComponent(filename)}`,
    {
      method: "GET",
      headers: {
        // 如果有认证 token，需要一起发
        // Authorization: `Bearer ${yourToken}`,
      },
    }
  );

  if (!res.ok) {
    throw new Error("下载失败");
  }

  // 把响应转成 blob，然后用 a 标签触发下载
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

export interface Document {
  id: string;
  title: string;
  filename: string;
  content: string;
  created_at: string;
  content_type: string;
  file_path: string;
  category?: string;
  doc_type?: string;
}

export class DocumentService {
  private baseUrl = `${API_BASE_URL}/api/v1/documents`;
  private axios = axios;

  async uploadDocument(formData: FormData): Promise<Document> {
    try {
      const response = await this.axios.post(`${this.baseUrl}/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      if (response.data.status === 'error') {
        throw new Error(response.data.message);
      }
      return response.data.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        throw new Error(error.response?.data?.message || '文件上传失败');
      }
      throw error;
    }
  }

  async listDocuments(params?: {
    limit?: number;
    category?: string;
  }): Promise<Document[]> {
    try {
      const response = await this.axios.get(`${this.baseUrl}/list`, { params });
      return response.data.data || [];
    } catch (error) {
      if (axios.isAxiosError(error)) {
        throw new Error(error.response?.data?.message || '获取文档列表失败');
      }
      throw error;
    }
  }

  async searchDocuments(query: string): Promise<Document[]> {
    try {
      const response = await this.axios.get(`${this.baseUrl}/search`, {
        params: { query }
      });
      return response.data.data || [];
    } catch (error) {
      if (axios.isAxiosError(error)) {
        throw new Error(error.response?.data?.message || '搜索文档失败');
      }
      throw error;
    }
  }
}
