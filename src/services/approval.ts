import axios from 'axios';
import { API_BASE_URL } from '../config';

export interface ApprovalItem {
  id: number;
  title: string;
  applicant: string;
  department: string;
  status: string;
  submitted_at: string;
  // …和 list_approvals 接口返回字段对应
}

export interface ApprovalDetail {
  id: number;
  title: string;
  applicant: string;
  department: string;
  status: string;
  submitted_at: string;
  steps: Array<{
    id: number;
    operator: string;
    time: string;
    opinion: string;
  }>;
  // …和 get_approval 返回的字段对应
}

/** 获取审批列表 */
export async function listApprovals(
  params?: { status?: string; department?: string; applicant?: string }
): Promise<ApprovalItem[]> {
  const res = await axios.get<ApprovalItem[]>(
    `${API_BASE_URL}/approvals`,
    { params }
  );
  return res.data;
}

/** 获取某条审批详情 */
export async function fetchApprovalById(id: number): Promise<ApprovalDetail> {
  const res = await axios.get<ApprovalDetail>(
    `${API_BASE_URL}/approvals/${id}`
  );
  return res.data;
}
