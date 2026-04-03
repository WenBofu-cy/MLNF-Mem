"""
MLNF-Mem V2.0 记忆中枢完整实现
原创提出者：文波福 | CC BY 4.0
包含：五层漏斗、晋升、遗忘、宏观自收敛合并
"""

import time
import uuid
import re
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

# ==================== 基础数据结构 ====================

class MemoryLevel(Enum):
    L1_TEMPORARY = 1   # 临时层
    L2_RECENT = 2      # 近期层
    L3_MIDTERM = 3     # 中期层
    L4_LONGTERM = 4    # 长期层
    L5_CORE = 5        # 核心层（永不遗忘）

@dataclass
class MemoryItem:
    """单条记忆"""
    id: str
    content: Any
    level: MemoryLevel
    importance: float = 0.0          # I
    reuse_count: int = 0             # C
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    significance_signal: float = 0.0  # S (情绪等价信号)
    meaning_label: float = 0.0        # V (意义标签)

    def update_importance(self, alpha=0.3, beta=0.3, gamma=0.4):
        self.importance += alpha * self.significance_signal + beta * self.meaning_label + gamma * self.reuse_count
        self.importance = min(1.0, self.importance)

# ==================== 子漏斗 ====================

class SubFunnel:
    """动态子漏斗：对应特定场景/对象"""
    def __init__(self, scene_key: str, parent: 'MLNFMem'):
        self.scene_key = scene_key
        self.parent = parent
        self.memory_layers: Dict[MemoryLevel, List[MemoryItem]] = {level: [] for level in MemoryLevel}
        self.last_active = time.time()
        # 晋升阈值 (时间秒, 重要度)
        self.promotion_thresholds = {
            MemoryLevel.L1_TEMPORARY: (30, 0.3),
            MemoryLevel.L2_RECENT: (3600, 0.5),
            MemoryLevel.L3_MIDTERM: (86400, 0.7),
            MemoryLevel.L4_LONGTERM: (604800, 0.9),
        }

    def add_memory(self, item: MemoryItem):
        item.level = MemoryLevel.L1_TEMPORARY
        self.memory_layers[item.level].append(item)
        self.last_active = time.time()

    def access(self, mem_id: str) -> Optional[MemoryItem]:
        for level in MemoryLevel:
            for mem in self.memory_layers[level]:
                if mem.id == mem_id:
                    mem.last_accessed = time.time()
                    mem.reuse_count += 1
                    mem.update_importance()
                    self.last_active = time.time()
                    return mem
        return None

    def promote(self):
        """晋升满足条件的记忆到更高层"""
        for from_level, to_level in [
            (MemoryLevel.L1_TEMPORARY, MemoryLevel.L2_RECENT),
            (MemoryLevel.L2_RECENT, MemoryLevel.L3_MIDTERM),
            (MemoryLevel.L3_MIDTERM, MemoryLevel.L4_LONGTERM),
            (MemoryLevel.L4_LONGTERM, MemoryLevel.L5_CORE),
        ]:
            t_sec, t_imp = self.promotion_thresholds[from_level]
            now = time.time()
            promoted = []
            for mem in self.memory_layers[from_level]:
                if (now - mem.created_at > t_sec) and (mem.importance > t_imp):
                    mem.level = to_level
                    self.memory_layers[to_level].append(mem)
                    promoted.append(mem)
            for mem in promoted:
                self.memory_layers[from_level].remove(mem)

    def forget(self, threshold=0.1):
        """遗忘低重要度记忆（L5 永不遗忘）"""
        for level in [MemoryLevel.L1_TEMPORARY, MemoryLevel.L2_RECENT,
                      MemoryLevel.L3_MIDTERM, MemoryLevel.L4_LONGTERM]:
            self.memory_layers[level] = [m for m in self.memory_layers[level] if m.importance >= threshold]

    def get_keywords(self) -> Set[str]:
        """提取子漏斗中所有记忆的关键词（用于合并相似度）"""
        kw = set()
        for level in MemoryLevel:
            for mem in self.memory_layers[level]:
                if isinstance(mem.content, str):
                    kw.update(re.findall(r'\w+', mem.content.lower()))
        return kw

    def all_memories(self) -> List[MemoryItem]:
        """返回所有记忆（用于合并）"""
        result = []
        for level in MemoryLevel:
            result.extend(self.memory_layers[level])
        return result

# ==================== 总控漏斗 ====================

class TotalController:
    def __init__(self, memory_system: 'MLNFMem'):
        self.memory_system = memory_system

    def cleanup_idle_funnels(self, idle_seconds=7*86400):
        """删除长期未使用的子漏斗"""
        now = time.time()
        to_delete = [k for k, f in self.memory_system.sub_funnels.items()
                     if now - f.last_active > idle_seconds]
        for k in to_delete:
            del self.memory_system.sub_funnels[k]

    def safety_check(self, action: Any) -> bool:
        """全局安全规则（示例）"""
        dangerous = ["harm", "attack", "hurt", "kill", "danger"]
        return not any(d in str(action).lower() for d in dangerous)

# ==================== 记忆中枢主类 ====================

class MLNFMem:
    def __init__(self, max_sub_funnels: int = 20):
        self.max_sub_funnels = max_sub_funnels
        self.total_ctl = TotalController(self)
        self.sub_funnels: Dict[str, SubFunnel] = {}

    def get_or_create(self, scene: str) -> SubFunnel:
        if scene in self.sub_funnels:
            return self.sub_funnels[scene]
        if len(self.sub_funnels) >= self.max_sub_funnels:
            self._merge_similar()
        funnel = SubFunnel(scene, self)
        self.sub_funnels[scene] = funnel
        return funnel

    def _merge_similar(self):
        """宏观自收敛：合并最相似的两个子漏斗（基于关键词 Jaccard 相似度）"""
        if len(self.sub_funnels) < 2:
            return
        funs = list(self.sub_funnels.items())
        best_sim = -1
        best_pair = None
        for i in range(len(funs)):
            for j in range(i+1, len(funs)):
                kw1 = funs[i][1].get_keywords()
                kw2 = funs[j][1].get_keywords()
                inter = len(kw1 & kw2)
                union = len(kw1 | kw2)
                sim = inter / union if union > 0 else 0
                if sim > best_sim:
                    best_sim = sim
                    best_pair = (i, j)
        if best_pair:
            i, j = best_pair
            key1, funnel1 = funs[i]
            key2, funnel2 = funs[j]
            # 将 funnel2 的所有记忆移动到 funnel1
            for mem in funnel2.all_memories():
                funnel1.add_memory(mem)
            del self.sub_funnels[key2]
            print(f"[宏观自收敛] 合并了场景 '{key2}' 到 '{key1}'，相似度 {best_sim:.2f}")

    def maintenance(self):
        """定期维护：晋升、遗忘、清理闲置"""
        for funnel in self.sub_funnels.values():
            funnel.promote()
            funnel.forget()
        self.total_ctl.cleanup_idle_funnels()
