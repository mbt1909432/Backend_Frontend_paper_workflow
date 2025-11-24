"""安全相关工具：密码哈希、JWT令牌等"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config.settings import settings
from app.utils.logger import logger

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _preprocess_password(password: str) -> str:
    """
    预处理密码以解决 bcrypt 72 字节限制问题
    
    bcrypt 有一个限制：密码不能超过 72 字节。
    使用 SHA-256 先哈希密码，将任意长度的密码转换为固定 32 字节的哈希值，
    然后再用 bcrypt 进行二次哈希。这样既解决了长度限制，又保持了安全性。
    """
    # 记录原始密码信息
    original_length = len(password.encode('utf-8'))
    logger.info(f"密码预处理: 原始密码长度={original_length} 字节")
    
    # 使用 SHA-256 将密码转换为固定长度的哈希值（32 字节）
    sha256_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    preprocessed_length = len(sha256_hash.encode('utf-8'))
    
    logger.info(f"密码预处理: SHA-256 哈希后长度={preprocessed_length} 字节, 哈希值前8位={sha256_hash[:8]}...")
    
    return sha256_hash


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    logger.info("开始验证密码")
    # 先对明文密码进行预处理（SHA-256 哈希）
    preprocessed_password = _preprocess_password(plain_password)
    try:
        result = pwd_context.verify(preprocessed_password, hashed_password)
        logger.info(f"密码验证结果: {'成功' if result else '失败'}")
        return result
    except Exception as e:
        logger.error(f"密码验证时发生错误: {e}")
        raise


def get_password_hash(password: str) -> str:
    """
    生成密码哈希
    
    使用 SHA-256 + bcrypt 双重哈希：
    1. 先用 SHA-256 将密码转换为固定长度（避免 bcrypt 72 字节限制）
    2. 再用 bcrypt 进行二次哈希（提供盐值和慢速哈希）
    """
    logger.info("开始生成密码哈希")
    
    # 先对密码进行预处理（SHA-256 哈希）
    preprocessed_password = _preprocess_password(password)
    
    # 记录预处理后的密码信息（用于调试）
    preprocessed_bytes = preprocessed_password.encode('utf-8')
    logger.info(f"准备使用 bcrypt 哈希: 预处理后密码长度={len(preprocessed_bytes)} 字节")
    
    # 检查是否超过 72 字节限制
    if len(preprocessed_bytes) > 72:
        logger.error(f"错误: 预处理后的密码长度 {len(preprocessed_bytes)} 字节超过了 bcrypt 的 72 字节限制!")
        raise ValueError(f"预处理后的密码长度 {len(preprocessed_bytes)} 字节超过了 bcrypt 的 72 字节限制")
    
    try:
        # 使用 bcrypt 进行二次哈希
        hashed = pwd_context.hash(preprocessed_password)
        logger.info(f"密码哈希生成成功: 哈希值前20位={hashed[:20]}...")
        return hashed
    except Exception as e:
        logger.error(f"生成密码哈希时发生错误: {type(e).__name__}: {e}")
        logger.error(f"错误详情: 预处理密码长度={len(preprocessed_bytes)} 字节, 预处理密码前16位={preprocessed_password[:16]}...")
        raise


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """解码JWT访问令牌"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None

