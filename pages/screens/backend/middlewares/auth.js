const jwt = require('jsonwebtoken');
const { JWT_SECRET, NODE_ENV } = require('../config');
const User = require('../models/User');
const { Token } = require('../models'); // For token blacklisting

/**
 * Enhanced JWT Authentication Middleware
 * Features:
 * - Role-based access control
 * - Token blacklisting
 * - Refresh token support
 * - Device fingerprinting
 * - Security headers check
 */

const auth = (roles = []) => {
  return async (req, res, next) => {
    try {
      // 1. Get token from header/cookie
      let token = req.header('Authorization')?.replace('Bearer ', '') || 
                 req.cookies?.access_token;

      if (!token) {
        return res.status(401).json({ 
          error: 'Authentication required',
          code: 'NO_TOKEN'
        });
      }

      // 2. Verify token signature
      const decoded = jwt.verify(token, JWT_SECRET);

      // 3. Check if token is blacklisted
      const isBlacklisted = await Token.exists({ token, blacklisted: true });
      if (isBlacklisted) {
        return res.status(401).json({ 
          error: 'Invalid session', 
          code: 'TOKEN_BLACKLISTED' 
        });
      }

      // 4. Fetch user and validate
      const user = await User.findById(decoded.id).select('-password');
      if (!user) {
        return res.status(401).json({ 
          error: 'User not found', 
          code: 'USER_NOT_FOUND' 
        });
      }

      // 5. Check if password was changed after token issued
      if (user.passwordChangedAt && decoded.iat < user.passwordChangedAt.getTime() / 1000) {
        return res.status(401).json({ 
          error: 'Password changed. Please login again',
          code: 'PASSWORD_CHANGED'
        });
      }

      // 6. Role-based authorization
      if (roles.length && !roles.includes(decoded.role)) {
        return res.status(403).json({ 
          error: 'Insufficient permissions', 
          code: 'FORBIDDEN' 
        });
      }

      // 7. Device fingerprint verification (optional)
      const clientFingerprint = req.headers['x-device-fingerprint'];
      if (decoded.fingerprint && clientFingerprint !== decoded.fingerprint) {
        return res.status(401).json({ 
          error: 'Session compromised', 
          code: 'DEVICE_MISMATCH' 
        });
      }

      // 8. Security headers check in production
      if (NODE_ENV === 'production') {
        if (!req.secure) {
          return res.status(426).json({ 
            error: 'HTTPS required', 
            code: 'UPGRADE_HTTPS' 
          });
        }

        // Check for basic security headers
        const requiredHeaders = ['X-Content-Type-Options', 'X-Frame-Options'];
        const missingHeaders = requiredHeaders.filter(h => !req.header(h));
        if (missingHeaders.length > 0) {
          return res.status(400).json({ 
            error: 'Missing security headers', 
            details: missingHeaders 
          });
        }
      }

      // Attach user and token to request
      req.user = user;
      req.token = token;

      next();
    } catch (err) {
      // Handle different JWT errors specifically
      let status = 401;
      let error = 'Invalid token';
      let code = 'INVALID_TOKEN';

      if (err.name === 'TokenExpiredError') {
        status = 401;
        error = 'Token expired';
        code = 'TOKEN_EXPIRED';
      } else if (err.name === 'JsonWebTokenError') {
        status = 401;
        error = 'Malformed token';
        code = 'MALFORMED_TOKEN';
      }

      return res.status(status).json({ error, code });
    }
  };
};

// Helper middleware for token refresh
auth.refresh = async (req, res, next) => {
  const refreshToken = req.cookies?.refresh_token;
  if (!refreshToken) return res.status(401).json({ error: 'Refresh token required' });

  try {
    const decoded = jwt.verify(refreshToken, JWT_SECRET);
    const user = await User.findById(decoded.id);
    
    if (!user) throw new Error('User not found');
    
    // Generate new access token
    const newToken = jwt.sign(
      { 
        id: user._id, 
        role: user.role,
        fingerprint: req.headers['x-device-fingerprint'] 
      }, 
      JWT_SECRET, 
      { expiresIn: '15m' }
    );

    req.newToken = newToken;
    next();
  } catch (err) {
    res.status(401).json({ error: 'Invalid refresh token' });
  }
};

module.exports = auth;
