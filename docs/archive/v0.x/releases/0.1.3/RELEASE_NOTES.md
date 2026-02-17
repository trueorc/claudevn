# ClaudeVN Platform Release 0.1.3

## User Management & Scope System

**Release Date:** November 23, 2025

---

## 🎉 What's New

### User & Organization Management
Complete user administration system with hierarchical organization support, scope-based permissions, and intuitive UI.

### Scope Selector
Switch between different organizational contexts seamlessly from the user menu dropdown.

### Admin Dashboard Enhancements
Manage users and organizations with full CRUD operations, all scoped to your current organizational context.

---

## 🐛 Bug Fixes

- **Fixed User Creation Error**: Resolved 422 error when creating users from Admin Dashboard
- **Role Case Sensitivity**: Standardized role values to prevent validation errors

---

## 🚀 Quick Start

### First Time Setup

1. **Start the Platform**
   ```bash
   ./start_all.sh
   ```

2. **Access the UI**
   - Navigate to: http://localhost:8001
   - Default credentials: `admin` / `admin123`
   - **⚠️ Change password immediately**

3. **Explore Features**
   - Click your name (top right) to access scope selector
   - Navigate to "Manage" for admin dashboard
   - Create organizations and users

### For Existing Installations

1. **Update Code**
   ```bash
   git pull origin main
   ```

2. **Rebuild Frontend**
   ```bash
   cd marketplace/frontend && npm run build
   ```

3. **Restart Services**
   ```bash
   ./stop_all.sh && ./start_all.sh
   ```

---

## 📋 Key Features

### 🔐 Authentication & Sessions
- Session-based authentication with 24-hour tokens
- Login/logout functionality
- Automatic session persistence

### 👥 User Management
- Create, update, enable/disable users
- User profile management with avatars
- Organization membership assignment
- Scope-filtered user lists

### 🏢 Organization Management
- Hierarchical organization trees
- Create sub-organizations unlimited depth
- View and manage organization members
- Role-based permissions (Admin/User)

### 📍 Scope System
- Context-aware UI based on selected organization
- Dynamic permission enforcement
- Seamless scope switching
- Persistent scope selection

### 🎨 Modern UI
- Clean, professional design
- Responsive layout
- Intuitive navigation
- Real-time updates

---

## 🔄 What Changed

### Frontend
- 8 new React components
- Scope context for state management
- Enhanced styling and UX
- Integrated user menu with scope selector

### Backend
- 15+ new API endpoints
- 3 new service layers
- Authentication system
- System initialization utilities

### Documentation
- 7 new documentation files
- Component-specific guides
- System architecture docs
- API reference updates

---

## 📖 Documentation

### Getting Started
- [Quickstart Guide](../../marketplace/QUICKSTART.md)
- [README](../../marketplace/README.md)

### System Concepts
- [Scope System](../../marketplace/SCOPE_SYSTEM.md)
- [User & Organization System](../../marketplace/USER_ORG_SYSTEM.md)

### User Guides
- [Admin Dashboard](../../marketplace/docs/ADMIN_DASHBOARD.md)
- [User Profile](../../marketplace/docs/USER_PROFILE.md)

### Technical
- [Implementation Summary](../../marketplace/IMPLEMENTATION_SUMMARY.md)
- [Full Changelog](./CHANGELOG.md)

---

## ⚠️ Important Notes

### Security
- **Change default admin password** on first login
- Session tokens are stored in browser localStorage
- All API endpoints require authentication (except login)

### Browser Support
- Modern browsers (Chrome, Firefox, Safari, Edge)
- JavaScript must be enabled
- Cookies/localStorage must be enabled

### System Requirements
- Python 3.11+
- Node.js 20.17+ (for frontend development)
- 100MB disk space

---

## 🆘 Troubleshooting

### User Creation Not Working
- Verify you're logged in as an admin
- Check you have "Admin" role in current scope
- Review browser console for errors

### Scope Selector Not Appearing
- Refresh browser (Ctrl+F5 / Cmd+Shift+R)
- Clear browser cache
- Verify you're logged in

### Organizations Not Loading
- Check backend logs: `tail -f logs/marketplace.log`
- Verify services are running: `./status.sh`
- Restart services: `./stop_all.sh && ./start_all.sh`

### Need Help?
- Check documentation in `docs/` folder
- Review system logs
- Verify all dependencies are installed

---

## 🔮 Coming Soon

- Password reset functionality
- Email notifications
- Advanced search and filtering
- Bulk user operations
- Audit logging
- Enhanced security features

---

## 📊 By the Numbers

- **41 files** modified
- **8,625 lines** of code added
- **29 new files** created
- **8 components** built
- **15+ API endpoints** added
- **100% backward compatible**

---

## 🙏 Thank You

This release represents a significant milestone in the ClaudeVN platform. The user and organization management system provides a solid foundation for multi-tenant agent orchestration.

**Version:** 0.1.3  
**Next Version:** 0.1.4 (in development)  
**Branch:** main  
**Commit:** 01cf78c

---

*For detailed technical changes, see [CHANGELOG.md](./CHANGELOG.md)*

