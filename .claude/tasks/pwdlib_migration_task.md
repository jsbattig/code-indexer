# Task: Migrate from passlib to pwdlib for Password Hashing

## Problem Context
- passlib is abandoned (last update Oct 2020)
- Causes crashes with bcrypt 5.0 on Amazon Linux 2023
- Need to migrate to pwdlib, a modern actively-maintained replacement

## Critical Requirements

1. **Replace passlib with pwdlib in PasswordManager**
   - File: `src/code_indexer/server/auth/password_manager.py`
   - Maintain exact same API (no breaking changes)

2. **Update TestDataFactory and TestUser**
   - File: `tests/utils/test_data_factory.py`
   - Update both TestUser.verify_password() and TestDataFactory hash methods

3. **Update pyproject.toml dependency**
   - Change: `"passlib[bcrypt]>=1.7.4"` → `"pwdlib[bcrypt]>=0.2.0"`

4. **CRITICAL API DIFFERENCE**
   - passlib: `verify(password, hash)` - password first
   - pwdlib: `verify(hash, password)` - hash first
   - **ORDER IS REVERSED!**

5. **Use BcryptHash explicitly**
   - Required for backward compatibility with existing password hashes

6. **Ensure all existing tests pass**
   - No test modifications required
   - API compatibility must be maintained

## Key pwdlib API Pattern

```python
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHash

# Use bcrypt explicitly for backward compatibility
pwd_hash = PasswordHash((BcryptHash(),))

# Hashing
hash_value = pwd_hash.hash("password")

# Verification - NOTE THE ORDER: (hash, password)
is_valid = pwd_hash.verify(hash_value, "password")
```

## TDD Workflow

### Phase 1: RED - Write Failing Tests
1. Create new test file: `tests/unit/server/auth/test_pwdlib_migration.py`
2. Write tests that verify:
   - pwdlib can hash passwords
   - pwdlib can verify correct passwords
   - pwdlib rejects incorrect passwords
   - pwdlib is backward compatible with existing bcrypt hashes from passlib
   - PasswordManager API remains unchanged

### Phase 2: GREEN - Implement Migration
1. Update `pyproject.toml` dependency
2. Migrate `PasswordManager` to use pwdlib
3. Migrate `TestDataFactory` to use pwdlib
4. Migrate `TestUser` to use pwdlib

### Phase 3: REFACTOR - Verify and Clean
1. Run all existing auth tests
2. Verify no passlib imports remain
3. Run fast-automation.sh to ensure no regressions

## Affected Files

- `src/code_indexer/server/auth/password_manager.py` (main implementation)
- `tests/utils/test_data_factory.py` (TestUser and TestDataFactory classes)
- `pyproject.toml` (dependency update)
- `tests/unit/server/auth/test_pwdlib_migration.py` (new test file)

## Success Criteria

✅ All new pwdlib tests pass
✅ All existing auth tests pass without modification
✅ No passlib imports remain in codebase
✅ PasswordManager API unchanged
✅ Backward compatibility with existing bcrypt hashes maintained
✅ fast-automation.sh passes completely

## Important Notes

- pwdlib.verify() argument order is REVERSED from passlib
- Use BcryptHash explicitly to ensure backward compatibility
- All existing tests must pass without modification
- No breaking changes to public APIs
