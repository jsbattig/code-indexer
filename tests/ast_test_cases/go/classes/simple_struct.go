package models

import "fmt"

type User struct {
    ID       int    `json:"id"`
    Name     string `json:"name"`
    Email    string `json:"email"`
    IsActive bool   `json:"is_active"`
}

func (u *User) GetFullInfo() string {
    return fmt.Sprintf("User: %s (%s)", u.Name, u.Email)
}

func (u User) IsValid() bool {
    return u.Name != "" && u.Email != ""
}

func NewUser(name, email string) *User {
    return &User{
        Name:     name,
        Email:    email,
        IsActive: true,
    }
}