/**
 * 带超时控制的 fetch 封装
 * @param url 请求URL
 * @param options fetch 选项
 * @param timeoutMs 超时时间（毫秒），默认5分钟
 * @returns fetch Promise
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 300000 // 默认5分钟
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if ((error as Error).name === 'AbortError') {
      throw new Error(`请求超时（超过${timeoutMs / 1000}秒），请检查网络连接或稍后重试`);
    }
    throw error;
  }
}

/**
 * 预定义的超时时间常量
 */
export const TIMEOUT = {
  SHORT: 30000,      // 30秒 - 用于快速操作
  MEDIUM: 60000,     // 1分钟 - 用于中等操作
  LONG: 180000,      // 3分钟 - 用于耗时操作
  VERY_LONG: 300000, // 5分钟 - 用于非常耗时的操作（如加载大索引、AI分析）
  CHAT: 600000,      // 10分钟 - 用于深度研究等超长对话
};
