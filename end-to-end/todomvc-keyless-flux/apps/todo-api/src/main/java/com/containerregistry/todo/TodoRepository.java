package com.containerregistry.todo;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.transaction.annotation.Transactional;

public interface TodoRepository extends JpaRepository<Todo, Long> {

    @Transactional
    void deleteByCompleted(boolean completed);
}
